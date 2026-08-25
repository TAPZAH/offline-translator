#include "offline_translator/app_settings.hpp"
#include "offline_translator/argos_model_manager.hpp"
#include "offline_translator/autostart.hpp"
#include "offline_translator/clipboard.hpp"
#include "offline_translator/hotkey.hpp"
#include "offline_translator/nllb_model_manager.hpp"
#include "offline_translator/selection.hpp"
#include "offline_translator/translation_application.hpp"
#include "offline_translator/window_policy.hpp"

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <shellapi.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cwchar>
#include <exception>
#include <filesystem>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

namespace {

constexpr UINT kTranslateMessage = WM_APP + 1;
constexpr UINT kStatusMessage = WM_APP + 2;
constexpr UINT kPackageProgressMessage = WM_APP + 3;
constexpr UINT kPackageDoneMessage = WM_APP + 4;
constexpr UINT kTrayMessage = WM_APP + 10;
constexpr UINT kSelectionResultMessage = WM_APP + 11;
constexpr UINT kSelectionPollTimer = 1;
constexpr UINT kSelectionButtonHideTimer = 2;
constexpr int kEngineCombo = 1001;
constexpr int kSourceEdit = 1002;
constexpr int kTranslateButton = 1003;
constexpr int kResultEdit = 1004;
constexpr int kSourceLanguageCombo = 1005;
constexpr int kTargetLanguageCombo = 1006;
constexpr int kPackagesButton = 1007;
constexpr int kStatusLabel = 1008;
constexpr int kSettingsButton = 1009;
constexpr int kPackageList = 1101;
constexpr int kPackageInstallButton = 1102;
constexpr int kPackageUninstallButton = 1103;
constexpr int kPackageCloseButton = 1104;
constexpr int kSettingsPopupCtrl = 1201;
constexpr int kSettingsDoubleCtrlC = 1202;
constexpr int kSettingsClickToClose = 1203;
constexpr int kSettingsSelectable = 1204;
constexpr int kSettingsAutostart = 1205;
constexpr int kSettingsHotkeyEdit = 1206;
constexpr int kSettingsSave = 1207;
constexpr int kSettingsCancel = 1208;
constexpr int kResultCopyButton = 1302;
constexpr int kResultCloseButton = 1303;
constexpr int kShowWindowHotkey = 2001;
constexpr int kTrayOpen = 3001;
constexpr int kTrayAutostart = 3002;
constexpr int kTrayExit = 3003;
constexpr int kDefaultWindowWidth = 560;
constexpr int kDefaultWindowHeight = 450;
constexpr int kMinWindowWidth = 520;
constexpr int kMinWindowHeight = 400;

HWND g_engine_combo = nullptr;
HWND g_source_edit = nullptr;
HWND g_translate_button = nullptr;
HWND g_result_edit = nullptr;
HWND g_source_language_combo = nullptr;
HWND g_target_language_combo = nullptr;
HWND g_packages_button = nullptr;
HWND g_settings_button = nullptr;
HWND g_status_label = nullptr;
HWND g_package_list = nullptr;
HWND g_package_install = nullptr;
HWND g_package_uninstall = nullptr;
HWND g_package_status = nullptr;
HWND g_settings_popup_ctrl = nullptr;
HWND g_settings_double_ctrl_c = nullptr;
HWND g_settings_click_to_close = nullptr;
HWND g_settings_selectable = nullptr;
HWND g_settings_autostart = nullptr;
HWND g_settings_hotkey_edit = nullptr;
HWND g_selection_button = nullptr;
HWND g_result_popup = nullptr;
HWND g_popup_result_edit = nullptr;
HWND g_popup_copy_button = nullptr;
bool g_smoke_mode = false;
bool g_start_minimized = false;
bool g_tray_added = false;
HICON g_tray_icon = nullptr;
NOTIFYICONDATAW g_tray_data{};

struct LanguageOption {
    const char* code;
    const wchar_t* name;
};

constexpr LanguageOption kLanguages[]{
    {"en", L"English"},
    {"ru", L"Русский"},
    {"de", L"Deutsch"},
    {"fr", L"Français"},
    {"es", L"Español"},
    {"it", L"Italiano"},
    {"pt", L"Português"},
    {"zh", L"中文"},
    {"ja", L"日本語"},
    {"ko", L"한국어"},
    {"ar", L"العربية"},
    {"uk", L"Українська"},
    {"pl", L"Polski"},
    {"tr", L"Türkçe"},
    {"nl", L"Nederlands"},
    {"cs", L"Čeština"},
    {"sv", L"Svenska"},
    {"fi", L"Suomi"},
    {"el", L"Ελληνικά"},
    {"he", L"עברית"},
    {"hi", L"हिन्दी"},
    {"id", L"Bahasa Indonesia"},
    {"az", L"Azərbaycan"},
    {"be", L"Беларуская"},
    {"bg", L"Български"},
    {"bn", L"বাংলা"},
    {"bs", L"Bosanski"},
    {"ca", L"Català"},
    {"da", L"Dansk"},
    {"et", L"Eesti"},
    {"fa", L"فارسی"},
    {"gu", L"ગુજરાતી"},
    {"hr", L"Hrvatski"},
    {"hu", L"Magyar"},
    {"is", L"Íslenska"},
    {"kn", L"ಕನ್ನಡ"},
    {"lt", L"Lietuvių"},
    {"lv", L"Latviešu"},
    {"ml", L"മലയാളം"},
    {"ms", L"Bahasa Melayu"},
    {"mt", L"Malti"},
    {"nb", L"Norsk Bokmål"},
    {"nn", L"Norsk Nynorsk"},
    {"ro", L"Română"},
    {"sk", L"Slovenčina"},
    {"sl", L"Slovenščina"},
    {"sq", L"Shqip"},
    {"sr", L"Српски"},
    {"ta", L"தமிழ்"},
    {"te", L"తెలుగు"},
    {"th", L"ไทย"},
    {"vi", L"Tiếng Việt"},
    {"mk", L"Македонски"},
    {"gl", L"Galego"},
    {"ur", L"اردو"},
    {"ka", L"ქართული"},
};

struct StatusPayload {
    std::wstring text;
    bool failed{false};
};

struct PackageRow {
    bool nllb{false};
    std::string from_code;
    std::string to_code;
    std::wstring title;
    bool installed{false};
    bool incomplete{false};
};

struct GuiRuntime {
    std::mutex mutex;
    offline_translator::TranslationSession session;
    offline_translator::AppSettings settings;
    std::atomic<bool> busy{false};
    std::atomic<bool> closing{false};
    std::atomic<bool> packages_busy{false};
    std::atomic<bool> selection_busy{false};
    HWND main_window{nullptr};
    HWND packages_window{nullptr};
    HWND settings_window{nullptr};
    std::vector<PackageRow> package_rows;
};

struct SelectionMonitor {
    bool press_active{false};
    bool was_pressed{false};
    bool was_c_pressed{false};
    bool press_is_client{false};
    bool gesture_invalid{false};
    int press_x{0};
    int press_y{0};
    int last_up_x{0};
    int last_up_y{0};
    HWND press_hwnd{nullptr};
    HWND last_up_hwnd{nullptr};
    POINT press_origin{};
    double press_time{0};
    double last_up_time{0};
    double last_ctrl_c_time{0};
    std::wstring selected_text;
};

SelectionMonitor g_selection;

std::shared_ptr<GuiRuntime> g_runtime;

std::string to_utf8(const std::wstring& text) {
    if (text.empty()) {
        return {};
    }
    const int size = WideCharToMultiByte(
        CP_UTF8,
        0,
        text.data(),
        static_cast<int>(text.size()),
        nullptr,
        0,
        nullptr,
        nullptr);
    std::string result(size, '\0');
    WideCharToMultiByte(
        CP_UTF8,
        0,
        text.data(),
        static_cast<int>(text.size()),
        result.data(),
        size,
        nullptr,
        nullptr);
    return result;
}

std::wstring from_utf8(const std::string& text) {
    if (text.empty()) {
        return {};
    }
    const int size = MultiByteToWideChar(
        CP_UTF8,
        0,
        text.data(),
        static_cast<int>(text.size()),
        nullptr,
        0);
    std::wstring result(size, L'\0');
    MultiByteToWideChar(
        CP_UTF8,
        0,
        text.data(),
        static_cast<int>(text.size()),
        result.data(),
        size);
    return result;
}

std::wstring control_text(HWND control) {
    const int length = GetWindowTextLengthW(control);
    std::wstring text(length + 1, L'\0');
    GetWindowTextW(control, text.data(), length + 1);
    text.resize(length);
    return text;
}

std::wstring user_profile() {
    wchar_t buffer[MAX_PATH]{};
    const DWORD length = GetEnvironmentVariableW(
        L"USERPROFILE",
        buffer,
        static_cast<DWORD>(std::size(buffer)));
    return length == 0 ? L"." : std::wstring(buffer, length);
}

std::wstring executable_directory() {
    std::array<wchar_t, MAX_PATH> buffer{};
    const DWORD length = GetModuleFileNameW(
        nullptr,
        buffer.data(),
        static_cast<DWORD>(buffer.size()));
    if (length == 0 || length >= buffer.size()) {
        return {};
    }
    std::wstring path(buffer.data(), length);
    const auto separator = path.find_last_of(L"\\/");
    return separator == std::wstring::npos ? L"." : path.substr(0, separator);
}

std::wstring model_root(bool use_nllb) {
    const std::wstring portable_root = executable_directory() + L"\\data\\" +
        (use_nllb ? L"nllb-200" : L"argos-packages");
    if (GetFileAttributesW(portable_root.c_str()) != INVALID_FILE_ATTRIBUTES) {
        return portable_root;
    }
    const std::wstring profile = user_profile();
    return use_nllb
        ? profile + L"\\.local\\share\\offline-translator\\nllb-200"
        : profile + L"\\.local\\share\\argos-translate\\packages";
}

std::filesystem::path model_root_path(bool use_nllb) {
    return std::filesystem::path(model_root(use_nllb));
}

std::wstring clipboard_text() {
    offline_translator::Win32Clipboard clipboard;
    return clipboard.get_text();
}

double monotonic_seconds() {
    using clock = std::chrono::steady_clock;
    static const auto epoch = clock::now();
    return std::chrono::duration<double>(clock::now() - epoch).count();
}

bool key_down(int virtual_key) {
    return (GetAsyncKeyState(virtual_key) & 0x8000) != 0;
}

int language_index(std::string_view code) {
    for (std::size_t index = 0; index < std::size(kLanguages); ++index) {
        if (kLanguages[index].code == code) {
            return static_cast<int>(index);
        }
    }
    return -1;
}

std::string selected_language(HWND combo) {
    const LRESULT index = SendMessageW(combo, CB_GETCURSEL, 0, 0);
    if (index < 0 || index >= static_cast<LRESULT>(std::size(kLanguages))) {
        throw std::runtime_error("Не выбран язык");
    }
    return kLanguages[static_cast<std::size_t>(index)].code;
}

offline_translator::EngineKind selected_engine() {
    return SendMessageW(g_engine_combo, CB_GETCURSEL, 0, 0) == 1
        ? offline_translator::EngineKind::nllb
        : offline_translator::EngineKind::argos;
}

void select_language(HWND combo, const std::string& code, int fallback) {
    const int index = language_index(code);
    SendMessageW(
        combo,
        CB_SETCURSEL,
        index >= 0 ? index : fallback,
        0);
}

void set_status(const std::wstring& text) {
    if (g_status_label) {
        SetWindowTextW(g_status_label, text.c_str());
    }
}

void post_payload(HWND window, UINT message, std::wstring text, bool failed) {
    if (!window || !IsWindow(window) || (g_runtime && g_runtime->closing)) {
        return;
    }
    auto* payload = new StatusPayload{std::move(text), failed};
    if (!PostMessageW(
            window,
            message,
            0,
            reinterpret_cast<LPARAM>(payload))) {
        delete payload;
    }
}

void post_status(HWND window, const std::string& text) {
    post_payload(window, kStatusMessage, from_utf8(text), false);
}

void fill_language_combos() {
    SendMessageW(g_source_language_combo, CB_RESETCONTENT, 0, 0);
    SendMessageW(g_target_language_combo, CB_RESETCONTENT, 0, 0);
    for (const auto& language : kLanguages) {
        SendMessageW(
            g_source_language_combo,
            CB_ADDSTRING,
            0,
            reinterpret_cast<LPARAM>(language.name));
        SendMessageW(
            g_target_language_combo,
            CB_ADDSTRING,
            0,
            reinterpret_cast<LPARAM>(language.name));
    }
}

void apply_settings_to_ui(const offline_translator::AppSettings& settings) {
    SendMessageW(
        g_engine_combo,
        CB_SETCURSEL,
        settings.engine == "nllb" ? 1 : 0,
        0);
    fill_language_combos();
    select_language(g_source_language_combo, settings.source_language, 0);
    select_language(
        g_target_language_combo,
        settings.target_language,
        std::size(kLanguages) > 1 ? 1 : 0);
}

void collect_window_size(HWND window, offline_translator::AppSettings& settings) {
    RECT bounds{};
    if (GetWindowRect(window, &bounds)) {
        settings.window_width = bounds.right - bounds.left;
        settings.window_height = bounds.bottom - bounds.top;
    }
}

offline_translator::AppSettings current_settings(HWND window) {
    offline_translator::AppSettings settings =
        g_runtime ? g_runtime->settings : offline_translator::AppSettings{};
    settings.engine =
        offline_translator::settings_engine_name(selected_engine());
    settings.source_language = selected_language(g_source_language_combo);
    settings.target_language = selected_language(g_target_language_combo);
    collect_window_size(window, settings);
    return settings;
}

void persist_settings(HWND window) {
    if (g_smoke_mode || !g_engine_combo) {
        return;
    }
    try {
        auto settings = current_settings(window);
        offline_translator::save_settings(settings);
        if (g_runtime) {
            g_runtime->settings = settings;
        }
    } catch (const std::exception&) {
        // Сохранение не должно ронять интерфейс.
    }
}

void set_main_busy(bool busy) {
    EnableWindow(g_translate_button, !busy);
    EnableWindow(g_engine_combo, !busy);
    EnableWindow(g_source_language_combo, !busy);
    EnableWindow(g_target_language_combo, !busy);
    EnableWindow(g_packages_button, !busy);
}

void layout_main(HWND window) {
    RECT client{};
    GetClientRect(window, &client);
    const int width = client.right - client.left;
    const int height = client.bottom - client.top;
    const int content_width = width - 32;
    const int status_top = height - 28;
    const int result_top = 228;
    int result_height = status_top - result_top - 8;
    if (result_height < 60) {
        result_height = 60;
    }
    if (g_packages_button) {
        SetWindowPos(
            g_packages_button,
            nullptr,
            width - 16 - 110,
            12,
            110,
            28,
            SWP_NOZORDER);
    }
    if (g_settings_button) {
        SetWindowPos(
            g_settings_button,
            nullptr,
            width - 16 - 110 - 8 - 110,
            12,
            110,
            28,
            SWP_NOZORDER);
    }
    if (g_source_edit) {
        SetWindowPos(
            g_source_edit,
            nullptr,
            16,
            84,
            content_width,
            90,
            SWP_NOZORDER);
    }
    if (g_result_edit) {
        SetWindowPos(
            g_result_edit,
            nullptr,
            16,
            result_top,
            content_width,
            result_height,
            SWP_NOZORDER);
    }
    if (g_status_label) {
        SetWindowPos(
            g_status_label,
            nullptr,
            16,
            status_top,
            content_width,
            20,
            SWP_NOZORDER);
    }
}

void start_translation(HWND window) {
    if (!g_runtime || g_runtime->busy.exchange(true)) {
        return;
    }
    const std::wstring source_text = control_text(g_source_edit);
    const auto engine_kind = selected_engine();
    const std::string source_language = selected_language(
        g_source_language_combo);
    const std::string target_language = selected_language(
        g_target_language_combo);
    const std::string text = to_utf8(source_text);
    const auto root = model_root_path(engine_kind == offline_translator::EngineKind::nllb);
    persist_settings(window);
    set_main_busy(true);
    set_status(L"Подготовка перевода...");
    auto runtime = g_runtime;
    std::thread(
        [window, text, root, engine_kind, source_language, target_language, runtime]() {
            auto result = std::make_unique<StatusPayload>();
            try {
                std::lock_guard lock(runtime->mutex);
                if (runtime->closing) {
                    runtime->busy = false;
                    return;
                }
                auto& application = runtime->session.acquire(engine_kind, root);
                if (!runtime->session.is_loaded()) {
                    post_status(window, "Загрузка модели...");
                } else {
                    post_status(window, "Перевод выполняется...");
                }
                result->text = from_utf8(
                    application.translate(
                        text,
                        source_language,
                        target_language)
                        .text);
                runtime->session.mark_loaded();
                post_status(window, "Готово");
            } catch (const std::exception& error) {
                result->failed = true;
                result->text = from_utf8(error.what());
                post_status(window, "Ошибка перевода");
            }
            runtime->busy = false;
            if (runtime->closing || !IsWindow(window)) {
                return;
            }
            PostMessageW(
                window,
                kTranslateMessage,
                0,
                reinterpret_cast<LPARAM>(result.release()));
        })
        .detach();
}

std::wstring package_status_text(const PackageRow& row) {
    if (row.installed) {
        return L"установлено";
    }
    if (row.incomplete) {
        return L"незавершённая загрузка";
    }
    return L"не установлено";
}

std::vector<PackageRow> collect_package_rows() {
    std::vector<PackageRow> rows;
    const auto nllb_root = model_root_path(true);
    offline_translator::NllbModelManager nllb(nllb_root);
    PackageRow nllb_row;
    nllb_row.nllb = true;
    nllb_row.title = L"NLLB-200 Distilled 600M";
    nllb_row.installed = nllb.is_installed();
    nllb_row.incomplete = nllb.has_incomplete_package();
    rows.push_back(std::move(nllb_row));

    const auto argos_root = model_root_path(false);
    auto add_argos = [&](const std::string& from_code,
                         const std::string& to_code,
                         const std::wstring& title) {
        offline_translator::ArgosModelManager manager(
            argos_root,
            from_code,
            to_code);
        PackageRow row;
        row.from_code = from_code;
        row.to_code = to_code;
        row.title = title;
        row.installed = manager.is_installed();
        row.incomplete = manager.has_incomplete_package();
        rows.push_back(std::move(row));
    };
    for (const auto& item :
         offline_translator::ArgosModelManager::available_packages()) {
        add_argos(
            item.from_code,
            item.to_code,
            L"Argos " + from_utf8(item.from_code) + L" → " +
                from_utf8(item.to_code));
    }
    for (const auto& item :
         offline_translator::ArgosModelManager::installed_packages(argos_root)) {
        bool already = false;
        for (const auto& row : rows) {
            if (!row.nllb && row.from_code == item.from_code &&
                row.to_code == item.to_code) {
                already = true;
                break;
            }
        }
        if (!already) {
            add_argos(
                item.from_code,
                item.to_code,
                L"Argos " + from_utf8(item.from_code) + L" → " +
                    from_utf8(item.to_code));
        }
    }
    return rows;
}

void refresh_package_list() {
    if (!g_package_list || !g_runtime) {
        return;
    }
    g_runtime->package_rows = collect_package_rows();
    SendMessageW(g_package_list, LB_RESETCONTENT, 0, 0);
    for (const auto& row : g_runtime->package_rows) {
        const std::wstring line =
            row.title + L" — " + package_status_text(row);
        SendMessageW(
            g_package_list,
            LB_ADDSTRING,
            0,
            reinterpret_cast<LPARAM>(line.c_str()));
    }
    if (!g_runtime->package_rows.empty()) {
        SendMessageW(g_package_list, LB_SETCURSEL, 0, 0);
    }
}

const PackageRow* selected_package_row() {
    if (!g_runtime || !g_package_list) {
        return nullptr;
    }
    const LRESULT index = SendMessageW(g_package_list, LB_GETCURSEL, 0, 0);
    if (index < 0 ||
        static_cast<std::size_t>(index) >= g_runtime->package_rows.size()) {
        return nullptr;
    }
    return &g_runtime->package_rows[static_cast<std::size_t>(index)];
}

void set_packages_busy(bool busy) {
    EnableWindow(g_package_install, !busy);
    EnableWindow(g_package_uninstall, !busy);
    EnableWindow(g_package_list, !busy);
}

void start_package_job(HWND packages_window, bool install) {
    if (!g_runtime) {
        return;
    }
    const PackageRow* selected = selected_package_row();
    if (!selected) {
        MessageBoxW(
            packages_window,
            L"Выберите пакет.",
            L"Пакеты",
            MB_ICONINFORMATION | MB_OK);
        return;
    }
    const PackageRow row = *selected;
    if (install && row.installed) {
        MessageBoxW(
            packages_window,
            L"Этот пакет уже установлен.",
            L"Пакеты",
            MB_ICONINFORMATION | MB_OK);
        return;
    }
    if (!install && !row.installed && !row.incomplete) {
        MessageBoxW(
            packages_window,
            L"Нечего удалять: пакет не установлен.",
            L"Пакеты",
            MB_ICONINFORMATION | MB_OK);
        return;
    }
    if (install && row.nllb) {
        const int answer = MessageBoxW(
            packages_window,
            L"Скачать модель NLLB-200 Distilled 600M (около 622 МБ)?\n"
            L"Это займёт время и место на диске.",
            L"Установка NLLB",
            MB_ICONWARNING | MB_YESNO);
        if (answer != IDYES) {
            return;
        }
    }
    if (!install && row.nllb) {
        const int answer = MessageBoxW(
            packages_window,
            L"Удалить установленную модель NLLB-200?\n"
            L"Это единственная модель NLLB; её придётся качать заново.",
            L"Удаление NLLB",
            MB_ICONWARNING | MB_YESNO);
        if (answer != IDYES) {
            return;
        }
    }
    if (!install && !row.nllb) {
        const std::wstring question =
            L"Удалить пакет " + row.title + L"?";
        const int answer = MessageBoxW(
            packages_window,
            question.c_str(),
            L"Удаление Argos",
            MB_ICONQUESTION | MB_YESNO);
        if (answer != IDYES) {
            return;
        }
    }
    if (g_runtime->packages_busy.exchange(true)) {
        return;
    }
    set_packages_busy(true);
    if (g_package_status) {
        SetWindowTextW(
            g_package_status,
            install ? L"Установка пакета..." : L"Удаление пакета...");
    }
    auto runtime = g_runtime;
    std::thread([packages_window, install, row, runtime]() {
        auto done = std::make_unique<StatusPayload>();
        try {
            std::lock_guard lock(runtime->mutex);
            runtime->session.reset();
            const auto progress =
                [packages_window, runtime](
                    std::uint64_t downloaded,
                    std::uint64_t total,
                    std::string_view message) {
                    if (runtime->closing || !IsWindow(packages_window)) {
                        return;
                    }
                    std::string text(message);
                    if (total > 0) {
                        const int percent = static_cast<int>(
                            (downloaded * 100) / total);
                        text += " (" + std::to_string(percent) + "%)";
                    }
                    post_payload(
                        packages_window,
                        kPackageProgressMessage,
                        from_utf8(text),
                        false);
                };
            if (row.nllb) {
                offline_translator::NllbModelManager manager(
                    model_root_path(true));
                if (install) {
                    manager.download_and_install(progress);
                } else {
                    manager.uninstall();
                }
            } else {
                offline_translator::ArgosModelManager manager(
                    model_root_path(false),
                    row.from_code,
                    row.to_code);
                if (install) {
                    manager.download_and_install(progress);
                } else {
                    manager.uninstall();
                }
            }
            done->text = install
                ? L"Пакет установлен."
                : L"Пакет удалён.";
        } catch (const std::exception& error) {
            done->failed = true;
            done->text = from_utf8(error.what());
        }
        runtime->packages_busy = false;
        if (runtime->closing || !IsWindow(packages_window)) {
            return;
        }
        PostMessageW(
            packages_window,
            kPackageDoneMessage,
            0,
            reinterpret_cast<LPARAM>(done.release()));
    }).detach();
}

HINSTANCE window_instance(HWND window) {
    return reinterpret_cast<HINSTANCE>(GetWindowLongPtrW(window, GWLP_HINSTANCE));
}

std::wstring find_app_icon_path() {
    const std::wstring exe_dir = executable_directory();
    std::vector<std::wstring> candidates{
        exe_dir + L"\\assets\\app.ico",
        exe_dir + L"\\app.ico",
    };
    std::wstring walk = exe_dir;
    for (int step = 0; step < 8; ++step) {
        candidates.push_back(walk + L"\\assets\\app.ico");
        const auto separator = walk.find_last_of(L"\\/");
        if (separator == std::wstring::npos) {
            break;
        }
        walk = walk.substr(0, separator);
    }
    for (const auto& path : candidates) {
        if (GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES) {
            return path;
        }
    }
    return {};
}

HICON create_generated_icon() {
    HDC screen = GetDC(nullptr);
    HDC memory = CreateCompatibleDC(screen);
    HBITMAP color = CreateCompatibleBitmap(screen, 16, 16);
    HBITMAP mask = CreateBitmap(16, 16, 1, 1, nullptr);
    HGDIOBJ old = SelectObject(memory, color);
    HBRUSH brush = CreateSolidBrush(RGB(45, 106, 227));
    RECT bounds{0, 0, 16, 16};
    FillRect(memory, &bounds, brush);
    DeleteObject(brush);
    SelectObject(memory, old);
    DeleteDC(memory);
    ReleaseDC(nullptr, screen);
    ICONINFO info{};
    info.fIcon = TRUE;
    info.hbmMask = mask;
    info.hbmColor = color;
    HICON icon = CreateIconIndirect(&info);
    DeleteObject(color);
    DeleteObject(mask);
    return icon;
}

HICON load_tray_icon() {
    const std::wstring path = find_app_icon_path();
    if (!path.empty()) {
        HICON icon = static_cast<HICON>(LoadImageW(
            nullptr,
            path.c_str(),
            IMAGE_ICON,
            16,
            16,
            LR_LOADFROMFILE));
        if (icon) {
            return icon;
        }
    }
    return create_generated_icon();
}

void add_tray_icon(HWND window) {
    if (g_smoke_mode || g_tray_added) {
        return;
    }
    if (!g_tray_icon) {
        g_tray_icon = load_tray_icon();
    }
    ZeroMemory(&g_tray_data, sizeof(g_tray_data));
    g_tray_data.cbSize = sizeof(g_tray_data);
    g_tray_data.hWnd = window;
    g_tray_data.uID = 1;
    g_tray_data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP;
    g_tray_data.uCallbackMessage = kTrayMessage;
    g_tray_data.hIcon = g_tray_icon;
    wcscpy_s(g_tray_data.szTip, L"Offline Translator");
    if (Shell_NotifyIconW(NIM_ADD, &g_tray_data)) {
        g_tray_added = true;
    }
}

void remove_tray_icon() {
    if (!g_tray_added) {
        return;
    }
    Shell_NotifyIconW(NIM_DELETE, &g_tray_data);
    g_tray_added = false;
}

void restore_from_tray(HWND window) {
    ShowWindow(window, SW_SHOWNORMAL);
    ShowWindow(window, SW_RESTORE);
    SetForegroundWindow(window);
    if (g_source_edit) {
        SetFocus(g_source_edit);
    }
}

void hide_to_tray(HWND window) {
    persist_settings(window);
    ShowWindow(window, SW_HIDE);
    add_tray_icon(window);
}

void destroy_popup_windows() {
    if (g_selection_button) {
        DestroyWindow(g_selection_button);
        g_selection_button = nullptr;
    }
    if (g_result_popup) {
        DestroyWindow(g_result_popup);
        g_result_popup = nullptr;
        g_popup_result_edit = nullptr;
        g_popup_copy_button = nullptr;
    }
}

bool register_translate_hotkey(HWND window, const std::string& spec) {
    UnregisterHotKey(window, kShowWindowHotkey);
    const auto parsed = offline_translator::parse_hotkey(spec);
    if (!parsed) {
        return false;
    }
    return RegisterHotKey(
               window,
               kShowWindowHotkey,
               offline_translator::hotkey_win32_modifiers(*parsed),
               parsed->vk) != FALSE;
}

void show_tray_menu(HWND window) {
    HMENU menu = CreatePopupMenu();
    if (!menu) {
        return;
    }
    AppendMenuW(menu, MF_STRING, kTrayOpen, L"Открыть");
    UINT autostart_flags = MF_STRING;
    try {
        if (offline_translator::is_app_autostart_enabled()) {
            autostart_flags |= MF_CHECKED;
        }
    } catch (const std::exception&) {
    }
    AppendMenuW(
        menu,
        autostart_flags,
        kTrayAutostart,
        L"Запускать вместе с Windows");
    AppendMenuW(menu, MF_STRING, kTrayExit, L"Выход");
    SetMenuDefaultItem(menu, kTrayOpen, FALSE);
    POINT cursor{};
    GetCursorPos(&cursor);
    SetForegroundWindow(window);
    TrackPopupMenu(
        menu,
        TPM_RIGHTBUTTON | TPM_BOTTOMALIGN,
        cursor.x,
        cursor.y,
        0,
        window,
        nullptr);
    DestroyMenu(menu);
}

void toggle_app_autostart() {
    try {
        const bool enabled = !offline_translator::is_app_autostart_enabled();
        offline_translator::set_app_autostart(enabled);
        set_status(
            enabled
                ? L"Программа будет запускаться вместе с Windows"
                : L"Программа убрана из автозагрузки");
    } catch (const std::exception& error) {
        set_status(from_utf8(error.what()));
    }
}

bool is_over_our_popup(int x, int y) {
    for (HWND candidate : {g_selection_button, g_result_popup}) {
        if (!candidate || !IsWindow(candidate) || !IsWindowVisible(candidate)) {
            continue;
        }
        RECT bounds{};
        GetWindowRect(candidate, &bounds);
        if (x >= bounds.left && x <= bounds.right && y >= bounds.top &&
            y <= bounds.bottom) {
            return true;
        }
    }
    return false;
}

bool is_client_hit(int x, int y, HWND hwnd) {
    if (!hwnd) {
        return false;
    }
    const LRESULT hit = SendMessageW(
        hwnd,
        WM_NCHITTEST,
        0,
        MAKELPARAM(static_cast<WORD>(x), static_cast<WORD>(y)));
    return hit == HTCLIENT;
}

bool window_being_moved() {
    HWND foreground = GetForegroundWindow();
    if (!foreground) {
        return false;
    }
    const DWORD thread_id = GetWindowThreadProcessId(foreground, nullptr);
    GUITHREADINFO info{};
    info.cbSize = sizeof(info);
    if (!GetGUIThreadInfo(thread_id, &info)) {
        return false;
    }
    return (info.flags & GUI_INMOVESIZE) != 0 || info.hwndMoveSize != nullptr;
}

void hide_selection_button() {
    if (g_runtime && g_runtime->main_window) {
        KillTimer(g_runtime->main_window, kSelectionButtonHideTimer);
    }
    if (g_selection_button) {
        DestroyWindow(g_selection_button);
        g_selection_button = nullptr;
    }
}

void hide_result_popup() {
    if (g_result_popup) {
        DestroyWindow(g_result_popup);
        g_result_popup = nullptr;
        g_popup_result_edit = nullptr;
        g_popup_copy_button = nullptr;
    }
}

LRESULT CALLBACK selection_button_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param);

LRESULT CALLBACK result_popup_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param);

void start_selection_translation(HWND main_window);

void show_selection_button(int cursor_x, int cursor_y, HWND main_window) {
    hide_result_popup();
    hide_selection_button();
    g_selection_button = CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
        L"OfflineTranslatorSelectionButton",
        L"Aa",
        WS_POPUP | WS_BORDER | WS_VISIBLE,
        cursor_x - 20,
        cursor_y - 20,
        40,
        40,
        main_window,
        nullptr,
        window_instance(main_window),
        nullptr);
    if (g_selection_button) {
        SetTimer(main_window, kSelectionButtonHideTimer, 8000, nullptr);
    }
}

void show_result_popup(
    HWND main_window,
    const std::wstring& text,
    const std::string& source_code,
    const std::string& target_code) {
    hide_selection_button();
    hide_result_popup();
    POINT cursor{};
    GetCursorPos(&cursor);
    const bool selectable = g_runtime &&
        g_runtime->settings.result_window_mode ==
            offline_translator::kResultWindowSelectable;
    const int width = 420;
    const int height = selectable ? 220 : 190;
    g_result_popup = CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
        L"OfflineTranslatorResultPopup",
        L"Перевод",
        WS_POPUP | WS_BORDER | WS_VISIBLE,
        cursor.x + 12,
        cursor.y + 12,
        width,
        height,
        main_window,
        nullptr,
        window_instance(main_window),
        nullptr);
    if (!g_result_popup) {
        return;
    }
    const std::wstring header = from_utf8(
        offline_translator::language_display_name(source_code) + " → " +
        offline_translator::language_display_name(target_code));
    CreateWindowW(
        L"STATIC",
        header.c_str(),
        WS_VISIBLE | WS_CHILD,
        12,
        8,
        390,
        18,
        g_result_popup,
        nullptr,
        nullptr,
        nullptr);
    DWORD edit_style = WS_VISIBLE | WS_CHILD | WS_BORDER | ES_MULTILINE |
        ES_AUTOVSCROLL | WS_VSCROLL | ES_READONLY;
    g_popup_result_edit = CreateWindowW(
        L"EDIT",
        text.c_str(),
        edit_style,
        12,
        30,
        390,
        110,
        g_result_popup,
        nullptr,
        nullptr,
        nullptr);
    g_popup_copy_button = CreateWindowW(
        L"BUTTON",
        L"Копировать",
        WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
        selectable ? 210 : 300,
        150,
        100,
        26,
        g_result_popup,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kResultCopyButton)),
        nullptr,
        nullptr);
    if (selectable) {
        CreateWindowW(
            L"BUTTON",
            L"Закрыть",
            WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
            318,
            150,
            84,
            26,
            g_result_popup,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kResultCloseButton)),
            nullptr,
            nullptr);
    }
}

void start_selection_translation(HWND main_window) {
    if (!g_runtime || g_runtime->selection_busy.exchange(true)) {
        return;
    }
    std::wstring selected = g_selection.selected_text;
    while (!selected.empty() &&
           (selected.back() == L' ' || selected.back() == L'\n')) {
        selected.pop_back();
    }
    if (selected.size() < 2) {
        g_runtime->selection_busy = false;
        return;
    }
    const std::string text = to_utf8(selected);
    const auto direction = offline_translator::choose_selection_direction(text);
    const auto engine_kind = selected_engine();
    const auto root = model_root_path(
        engine_kind == offline_translator::EngineKind::nllb);
    auto runtime = g_runtime;
    std::thread([main_window, text, direction, engine_kind, root, runtime]() {
        auto result = std::make_unique<StatusPayload>();
        try {
            std::lock_guard lock(runtime->mutex);
            if (runtime->closing) {
                runtime->selection_busy = false;
                return;
            }
            auto& application = runtime->session.acquire(engine_kind, root);
            result->text = from_utf8(
                application.translate(text, direction.first, direction.second)
                    .text);
            runtime->session.mark_loaded();
        } catch (const std::exception& error) {
            result->failed = true;
            result->text = from_utf8(std::string("Ошибка: ") + error.what());
        }
        runtime->selection_busy = false;
        if (runtime->closing || !IsWindow(main_window)) {
            return;
        }
        PostMessageW(
            main_window,
            kSelectionResultMessage,
            0,
            reinterpret_cast<LPARAM>(result.release()));
    }).detach();
}

void capture_and_show_button(HWND main_window, int cursor_x, int cursor_y) {
    try {
        const std::wstring selected =
            offline_translator::capture_selected_text_win32(main_window);
        if (selected.size() < 2) {
            return;
        }
        g_selection.selected_text = selected;
        show_selection_button(cursor_x, cursor_y, main_window);
    } catch (const std::exception&) {
    }
}

void poll_double_ctrl_c(HWND main_window) {
    if (!g_runtime || !g_runtime->settings.double_ctrl_c_translation) {
        g_selection.last_ctrl_c_time = 0;
        g_selection.was_c_pressed = key_down('C');
        return;
    }
    const bool ctrl_pressed = key_down(VK_CONTROL);
    const bool c_pressed = key_down('C');
    if (!ctrl_pressed) {
        g_selection.last_ctrl_c_time = 0;
    }
    if (c_pressed && !g_selection.was_c_pressed && ctrl_pressed) {
        const double now = monotonic_seconds();
        if (offline_translator::should_trigger_double_ctrl_c(
                g_selection.last_ctrl_c_time,
                now,
                ctrl_pressed,
                true)) {
            g_selection.last_ctrl_c_time = 0;
            try {
                const std::wstring selected = clipboard_text();
                if (selected.size() >= 2) {
                    g_selection.selected_text = selected;
                    hide_selection_button();
                    start_selection_translation(main_window);
                }
            } catch (const std::exception&) {
            }
        } else {
            g_selection.last_ctrl_c_time = now;
        }
    }
    g_selection.was_c_pressed = c_pressed;
}

void poll_selection(HWND main_window) {
    if (g_smoke_mode || !g_runtime) {
        return;
    }
    POINT cursor{};
    GetCursorPos(&cursor);
    poll_double_ctrl_c(main_window);
    const bool pressed = key_down(VK_LBUTTON);
    if (pressed && !g_selection.was_pressed) {
        if (is_over_our_popup(cursor.x, cursor.y)) {
            g_selection.press_active = false;
        } else {
            HWND hwnd = WindowFromPoint(cursor);
            g_selection.press_x = cursor.x;
            g_selection.press_y = cursor.y;
            g_selection.press_time = monotonic_seconds();
            g_selection.press_hwnd = hwnd ? GetAncestor(hwnd, GA_ROOT) : nullptr;
            RECT origin{};
            if (g_selection.press_hwnd &&
                GetWindowRect(g_selection.press_hwnd, &origin)) {
                g_selection.press_origin.x = origin.left;
                g_selection.press_origin.y = origin.top;
            } else {
                g_selection.press_origin = cursor;
            }
            g_selection.press_is_client = is_client_hit(cursor.x, cursor.y, hwnd);
            g_selection.gesture_invalid = !g_selection.press_is_client;
            g_selection.press_active = true;
        }
    } else if (pressed && g_selection.was_pressed && g_selection.press_active) {
        if (!g_selection.gesture_invalid) {
            if (window_being_moved()) {
                g_selection.gesture_invalid = true;
            } else if (g_selection.press_hwnd) {
                RECT origin{};
                if (GetWindowRect(g_selection.press_hwnd, &origin)) {
                    if (std::abs(origin.left - g_selection.press_origin.x) >= 4 ||
                        std::abs(origin.top - g_selection.press_origin.y) >= 4) {
                        g_selection.gesture_invalid = true;
                    }
                }
            }
        }
    } else if (!pressed && g_selection.was_pressed && g_selection.press_active) {
        const double now = monotonic_seconds();
        const int drag_distance = std::max(
            std::abs(cursor.x - g_selection.press_x),
            std::abs(cursor.y - g_selection.press_y));
        const double drag_duration = now - g_selection.press_time;
        bool window_moved = false;
        if (g_selection.press_hwnd) {
            RECT origin{};
            if (GetWindowRect(g_selection.press_hwnd, &origin)) {
                window_moved =
                    std::abs(origin.left - g_selection.press_origin.x) >= 4 ||
                    std::abs(origin.top - g_selection.press_origin.y) >= 4;
            }
        }
        const bool is_double_click =
            (now - g_selection.last_up_time) < 0.35 &&
            g_selection.press_hwnd != nullptr &&
            g_selection.press_hwnd == g_selection.last_up_hwnd &&
            std::abs(cursor.x - g_selection.last_up_x) <= 6 &&
            std::abs(cursor.y - g_selection.last_up_y) <= 6 &&
            g_selection.press_is_client;
        g_selection.last_up_time = now;
        g_selection.last_up_hwnd = g_selection.press_hwnd;
        g_selection.last_up_x = cursor.x;
        g_selection.last_up_y = cursor.y;
        if (!g_selection.gesture_invalid &&
            !is_over_our_popup(cursor.x, cursor.y) &&
            offline_translator::should_capture_selection(
                g_selection.press_is_client,
                window_moved,
                drag_distance,
                drag_duration,
                is_double_click) &&
            offline_translator::should_show_selection_button(
                g_runtime->settings.popup_requires_ctrl,
                key_down(VK_CONTROL))) {
            capture_and_show_button(main_window, cursor.x, cursor.y);
        }
        g_selection.press_active = false;
    }
    g_selection.was_pressed = pressed;
}

void handle_translate_hotkey(HWND window) {
    for (int step = 0; step < 25; ++step) {
        if (!key_down(VK_CONTROL) && !key_down(VK_SHIFT) &&
            !key_down(VK_MENU) && !key_down(VK_LWIN) && !key_down(VK_RWIN)) {
            break;
        }
        Sleep(20);
    }
    std::wstring previous;
    try {
        previous = clipboard_text();
    } catch (const std::exception&) {
    }
    std::wstring selected;
    try {
        selected = offline_translator::capture_selected_text_win32(window);
    } catch (const std::exception&) {
    }
    if (selected.size() < 2) {
        selected = previous;
    }
    if (selected.size() < 2) {
        set_status(L"Нет выделенного текста");
        return;
    }
    g_selection.selected_text = selected;
    if (IsWindowVisible(window) && g_source_edit) {
        SetWindowTextW(g_source_edit, selected.c_str());
    }
    start_selection_translation(window);
}

void close_settings_window();

LRESULT CALLBACK selection_button_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param) {
    if (message == WM_LBUTTONUP) {
        if (g_runtime) {
            start_selection_translation(g_runtime->main_window);
        }
        return 0;
    }
    if (message == WM_PAINT) {
        PAINTSTRUCT paint{};
        HDC dc = BeginPaint(window, &paint);
        RECT client{};
        GetClientRect(window, &client);
        SetBkMode(dc, TRANSPARENT);
        SetTextColor(dc, RGB(20, 20, 20));
        DrawTextW(dc, L"Aa", -1, &client, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        EndPaint(window, &paint);
        return 0;
    }
    if (message == WM_DESTROY) {
        if (g_selection_button == window) {
            g_selection_button = nullptr;
        }
        return 0;
    }
    return DefWindowProcW(window, message, w_param, l_param);
}

LRESULT CALLBACK result_popup_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param) {
    const bool click_to_close = !g_runtime ||
        g_runtime->settings.result_window_mode !=
            offline_translator::kResultWindowSelectable;
    if (message == WM_COMMAND) {
        const int id = LOWORD(w_param);
        if (id == kResultCopyButton) {
            const std::wstring text = g_popup_result_edit
                ? control_text(g_popup_result_edit)
                : std::wstring{};
            try {
                offline_translator::Win32Clipboard clipboard(window);
                clipboard.set_text(text);
            } catch (const std::exception&) {
            }
            return 0;
        }
        if (id == kResultCloseButton) {
            hide_result_popup();
            return 0;
        }
    }
    if (message == WM_LBUTTONUP && click_to_close) {
        hide_result_popup();
        return 0;
    }
    if (message == WM_PARENTNOTIFY && click_to_close &&
        LOWORD(w_param) == WM_LBUTTONDOWN) {
        const HWND child = reinterpret_cast<HWND>(l_param);
        if (child != g_popup_copy_button) {
            hide_result_popup();
        }
        return 0;
    }
    if (message == WM_DESTROY) {
        if (g_result_popup == window) {
            g_result_popup = nullptr;
            g_popup_result_edit = nullptr;
            g_popup_copy_button = nullptr;
        }
        return 0;
    }
    return DefWindowProcW(window, message, w_param, l_param);
}

void apply_settings_dialog(HWND settings_window) {
    if (!g_runtime) {
        return;
    }
    auto settings = g_runtime->settings;
    settings.popup_requires_ctrl =
        SendMessageW(g_settings_popup_ctrl, BM_GETCHECK, 0, 0) == BST_CHECKED;
    settings.double_ctrl_c_translation =
        SendMessageW(g_settings_double_ctrl_c, BM_GETCHECK, 0, 0) == BST_CHECKED;
    settings.result_window_mode =
        SendMessageW(g_settings_click_to_close, BM_GETCHECK, 0, 0) == BST_CHECKED
            ? std::string{offline_translator::kResultWindowClickToClose}
            : std::string{offline_translator::kResultWindowSelectable};
    const std::string hotkey = to_utf8(control_text(g_settings_hotkey_edit));
    if (!offline_translator::parse_hotkey(hotkey)) {
        MessageBoxW(
            settings_window,
            L"Некорректная горячая клавиша. Пример: Ctrl+Shift+T",
            L"Настройки",
            MB_ICONWARNING | MB_OK);
        return;
    }
    settings.translate_hotkey =
        offline_translator::format_hotkey(*offline_translator::parse_hotkey(hotkey));
    if (g_runtime->main_window && g_engine_combo) {
        settings.engine =
            offline_translator::settings_engine_name(selected_engine());
        settings.source_language = selected_language(g_source_language_combo);
        settings.target_language = selected_language(g_target_language_combo);
        collect_window_size(g_runtime->main_window, settings);
    }
    try {
        if (!g_smoke_mode) {
            offline_translator::save_settings(settings);
            const bool autostart =
                SendMessageW(g_settings_autostart, BM_GETCHECK, 0, 0) ==
                BST_CHECKED;
            offline_translator::set_app_autostart(autostart);
            if (g_runtime->main_window &&
                !register_translate_hotkey(
                    g_runtime->main_window,
                    settings.translate_hotkey)) {
                MessageBoxW(
                    settings_window,
                    L"Не удалось зарегистрировать горячую клавишу.",
                    L"Настройки",
                    MB_ICONWARNING | MB_OK);
            }
        }
        g_runtime->settings = settings;
        close_settings_window();
        set_status(L"Настройки сохранены");
    } catch (const std::exception& error) {
        MessageBoxW(
            settings_window,
            from_utf8(error.what()).c_str(),
            L"Настройки",
            MB_ICONERROR | MB_OK);
    }
}

void close_settings_window() {
    if (!g_runtime || !g_runtime->settings_window) {
        return;
    }
    HWND settings = g_runtime->settings_window;
    HWND main = g_runtime->main_window;
    g_runtime->settings_window = nullptr;
    g_settings_popup_ctrl = nullptr;
    g_settings_double_ctrl_c = nullptr;
    g_settings_click_to_close = nullptr;
    g_settings_selectable = nullptr;
    g_settings_autostart = nullptr;
    g_settings_hotkey_edit = nullptr;
    DestroyWindow(settings);
    if (main) {
        EnableWindow(main, TRUE);
        SetForegroundWindow(main);
    }
}

LRESULT CALLBACK settings_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param) {
    if (message == WM_CREATE) {
        const auto settings = g_runtime ? g_runtime->settings
                                        : offline_translator::AppSettings{};
        g_settings_popup_ctrl = CreateWindowW(
            L"BUTTON",
            L"Показывать кнопку выделения только при удержании Ctrl",
            WS_VISIBLE | WS_CHILD | BS_AUTOCHECKBOX,
            16,
            16,
            450,
            24,
            window,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSettingsPopupCtrl)),
            nullptr,
            nullptr);
        SendMessageW(
            g_settings_popup_ctrl,
            BM_SETCHECK,
            settings.popup_requires_ctrl ? BST_CHECKED : BST_UNCHECKED,
            0);
        g_settings_double_ctrl_c = CreateWindowW(
            L"BUTTON",
            L"Переводить выделенный текст по Ctrl+C+C",
            WS_VISIBLE | WS_CHILD | BS_AUTOCHECKBOX,
            16,
            48,
            450,
            24,
            window,
            reinterpret_cast<HMENU>(
                static_cast<INT_PTR>(kSettingsDoubleCtrlC)),
            nullptr,
            nullptr);
        SendMessageW(
            g_settings_double_ctrl_c,
            BM_SETCHECK,
            settings.double_ctrl_c_translation ? BST_CHECKED : BST_UNCHECKED,
            0);
        CreateWindowW(
            L"STATIC",
            L"Окно результата:",
            WS_VISIBLE | WS_CHILD,
            16,
            88,
            200,
            20,
            window,
            nullptr,
            nullptr,
            nullptr);
        g_settings_click_to_close = CreateWindowW(
            L"BUTTON",
            L"Закрывать нажатием по окну",
            WS_VISIBLE | WS_CHILD | BS_AUTORADIOBUTTON | WS_GROUP,
            16,
            112,
            300,
            22,
            window,
            reinterpret_cast<HMENU>(
                static_cast<INT_PTR>(kSettingsClickToClose)),
            nullptr,
            nullptr);
        g_settings_selectable = CreateWindowW(
            L"BUTTON",
            L"Выделять текст; закрывать кнопкой «Закрыть»",
            WS_VISIBLE | WS_CHILD | BS_AUTORADIOBUTTON,
            16,
            136,
            420,
            22,
            window,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSettingsSelectable)),
            nullptr,
            nullptr);
        const bool click_to_close = settings.result_window_mode !=
            offline_translator::kResultWindowSelectable;
        SendMessageW(
            g_settings_click_to_close,
            BM_SETCHECK,
            click_to_close ? BST_CHECKED : BST_UNCHECKED,
            0);
        SendMessageW(
            g_settings_selectable,
            BM_SETCHECK,
            click_to_close ? BST_UNCHECKED : BST_CHECKED,
            0);
        CreateWindowW(
            L"STATIC",
            L"Горячая клавиша перевода выделения:",
            WS_VISIBLE | WS_CHILD,
            16,
            176,
            300,
            20,
            window,
            nullptr,
            nullptr,
            nullptr);
        g_settings_hotkey_edit = CreateWindowW(
            L"EDIT",
            from_utf8(settings.translate_hotkey).c_str(),
            WS_VISIBLE | WS_CHILD | WS_BORDER | ES_AUTOHSCROLL,
            16,
            200,
            240,
            24,
            window,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSettingsHotkeyEdit)),
            nullptr,
            nullptr);
        g_settings_autostart = CreateWindowW(
            L"BUTTON",
            L"Запускать вместе с Windows",
            WS_VISIBLE | WS_CHILD | BS_AUTOCHECKBOX,
            16,
            240,
            400,
            24,
            window,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSettingsAutostart)),
            nullptr,
            nullptr);
        bool autostart = false;
        try {
            autostart = offline_translator::is_app_autostart_enabled();
        } catch (const std::exception&) {
        }
        SendMessageW(
            g_settings_autostart,
            BM_SETCHECK,
            autostart ? BST_CHECKED : BST_UNCHECKED,
            0);
        CreateWindowW(
            L"BUTTON",
            L"Сохранить",
            WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
            16,
            284,
            120,
            30,
            window,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSettingsSave)),
            nullptr,
            nullptr);
        CreateWindowW(
            L"BUTTON",
            L"Отмена",
            WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
            148,
            284,
            120,
            30,
            window,
            reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSettingsCancel)),
            nullptr,
            nullptr);
        return 0;
    }
    if (message == WM_COMMAND) {
        const int id = LOWORD(w_param);
        if (id == kSettingsSave) {
            apply_settings_dialog(window);
            return 0;
        }
        if (id == kSettingsCancel) {
            close_settings_window();
            return 0;
        }
    }
    if (message == WM_CLOSE) {
        close_settings_window();
        return 0;
    }
    if (message == WM_DESTROY) {
        if (g_runtime && g_runtime->settings_window == window) {
            g_runtime->settings_window = nullptr;
        }
        return 0;
    }
    return DefWindowProcW(window, message, w_param, l_param);
}

void open_settings_window(HWND parent, HINSTANCE instance) {
    if (g_runtime && g_runtime->settings_window) {
        SetForegroundWindow(g_runtime->settings_window);
        return;
    }
    HWND settings = CreateWindowW(
        L"OfflineTranslatorSettings",
        L"Настройки",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        520,
        370,
        parent,
        nullptr,
        instance,
        nullptr);
    if (!settings) {
        throw std::runtime_error("Не удалось открыть настройки");
    }
    if (g_runtime) {
        g_runtime->settings_window = settings;
    }
    EnableWindow(parent, FALSE);
    ShowWindow(settings, SW_SHOW);
    UpdateWindow(settings);
}

void create_main_controls(HWND window) {
    CreateWindowW(
        L"STATIC",
        L"Движок:",
        WS_VISIBLE | WS_CHILD,
        16,
        16,
        70,
        24,
        window,
        nullptr,
        nullptr,
        nullptr);
    g_engine_combo = CreateWindowW(
        L"COMBOBOX",
        nullptr,
        WS_VISIBLE | WS_CHILD | CBS_DROPDOWNLIST | WS_TABSTOP,
        90,
        12,
        140,
        160,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kEngineCombo)),
        nullptr,
        nullptr);
    SendMessageW(
        g_engine_combo,
        CB_ADDSTRING,
        0,
        reinterpret_cast<LPARAM>(L"Argos"));
    SendMessageW(
        g_engine_combo,
        CB_ADDSTRING,
        0,
        reinterpret_cast<LPARAM>(L"NLLB-200"));
    SendMessageW(g_engine_combo, CB_SETCURSEL, 0, 0);
    g_packages_button = CreateWindowW(
        L"BUTTON",
        L"Пакеты",
        WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON | WS_TABSTOP,
        390,
        12,
        110,
        28,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kPackagesButton)),
        nullptr,
        nullptr);
    g_settings_button = CreateWindowW(
        L"BUTTON",
        L"Настройки",
        WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON | WS_TABSTOP,
        272,
        12,
        110,
        28,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSettingsButton)),
        nullptr,
        nullptr);
    CreateWindowW(
        L"STATIC",
        L"С языка:",
        WS_VISIBLE | WS_CHILD,
        16,
        52,
        70,
        24,
        window,
        nullptr,
        nullptr,
        nullptr);
    g_source_language_combo = CreateWindowW(
        L"COMBOBOX",
        nullptr,
        WS_VISIBLE | WS_CHILD | CBS_DROPDOWNLIST | WS_TABSTOP,
        90,
        48,
        150,
        140,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSourceLanguageCombo)),
        nullptr,
        nullptr);
    CreateWindowW(
        L"STATIC",
        L"На язык:",
        WS_VISIBLE | WS_CHILD,
        270,
        52,
        60,
        24,
        window,
        nullptr,
        nullptr,
        nullptr);
    g_target_language_combo = CreateWindowW(
        L"COMBOBOX",
        nullptr,
        WS_VISIBLE | WS_CHILD | CBS_DROPDOWNLIST | WS_TABSTOP,
        335,
        48,
        130,
        140,
        window,
        reinterpret_cast<HMENU>(
            static_cast<INT_PTR>(kTargetLanguageCombo)),
        nullptr,
        nullptr);
    g_source_edit = CreateWindowW(
        L"EDIT",
        L"Hello world",
        WS_VISIBLE | WS_CHILD | WS_BORDER | ES_MULTILINE | ES_AUTOVSCROLL |
            WS_VSCROLL | WS_TABSTOP,
        16,
        84,
        470,
        90,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSourceEdit)),
        nullptr,
        nullptr);
    g_translate_button = CreateWindowW(
        L"BUTTON",
        L"Перевести",
        WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON | WS_TABSTOP,
        16,
        186,
        120,
        30,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kTranslateButton)),
        nullptr,
        nullptr);
    g_result_edit = CreateWindowW(
        L"EDIT",
        nullptr,
        WS_VISIBLE | WS_CHILD | WS_BORDER | ES_MULTILINE | ES_READONLY |
            ES_AUTOVSCROLL | WS_VSCROLL,
        16,
        228,
        470,
        140,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kResultEdit)),
        nullptr,
        nullptr);
    g_status_label = CreateWindowW(
        L"STATIC",
        L"Готово",
        WS_VISIBLE | WS_CHILD | SS_LEFT,
        16,
        378,
        470,
        20,
        window,
        reinterpret_cast<HMENU>(static_cast<INT_PTR>(kStatusLabel)),
        nullptr,
        nullptr);
    const auto settings = offline_translator::load_settings();
    if (g_runtime) {
        g_runtime->settings = settings;
    }
    apply_settings_to_ui(settings);
    layout_main(window);
}

void close_packages_window() {
    if (!g_runtime || !g_runtime->packages_window) {
        return;
    }
    HWND packages = g_runtime->packages_window;
    HWND main = g_runtime->main_window;
    g_runtime->packages_window = nullptr;
    g_package_list = nullptr;
    g_package_install = nullptr;
    g_package_uninstall = nullptr;
    g_package_status = nullptr;
    DestroyWindow(packages);
    if (main) {
        EnableWindow(main, TRUE);
        SetForegroundWindow(main);
    }
}

LRESULT CALLBACK packages_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param) {
    try {
        if (message == WM_CREATE) {
            CreateWindowW(
                L"STATIC",
                L"Установленные и доступные пакеты Argos/NLLB:",
                WS_VISIBLE | WS_CHILD,
                16,
                12,
                430,
                20,
                window,
                nullptr,
                nullptr,
                nullptr);
            g_package_list = CreateWindowW(
                L"LISTBOX",
                nullptr,
                WS_VISIBLE | WS_CHILD | WS_BORDER | WS_VSCROLL | LBS_NOTIFY |
                    WS_TABSTOP,
                16,
                36,
                450,
                210,
                window,
                reinterpret_cast<HMENU>(static_cast<INT_PTR>(kPackageList)),
                nullptr,
                nullptr);
            g_package_status = CreateWindowW(
                L"STATIC",
                L"",
                WS_VISIBLE | WS_CHILD | SS_LEFT,
                16,
                250,
                450,
                22,
                window,
                nullptr,
                nullptr,
                nullptr);
            g_package_install = CreateWindowW(
                L"BUTTON",
                L"Установить",
                WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON | WS_TABSTOP,
                16,
                280,
                120,
                30,
                window,
                reinterpret_cast<HMENU>(
                    static_cast<INT_PTR>(kPackageInstallButton)),
                nullptr,
                nullptr);
            g_package_uninstall = CreateWindowW(
                L"BUTTON",
                L"Удалить",
                WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON | WS_TABSTOP,
                148,
                280,
                120,
                30,
                window,
                reinterpret_cast<HMENU>(
                    static_cast<INT_PTR>(kPackageUninstallButton)),
                nullptr,
                nullptr);
            CreateWindowW(
                L"BUTTON",
                L"Закрыть",
                WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON | WS_TABSTOP,
                346,
                280,
                120,
                30,
                window,
                reinterpret_cast<HMENU>(
                    static_cast<INT_PTR>(kPackageCloseButton)),
                nullptr,
                nullptr);
            refresh_package_list();
            return 0;
        }
        if (message == WM_COMMAND) {
            const int id = LOWORD(w_param);
            if (id == kPackageCloseButton) {
                close_packages_window();
                return 0;
            }
            if (id == kPackageInstallButton) {
                start_package_job(window, true);
                return 0;
            }
            if (id == kPackageUninstallButton) {
                start_package_job(window, false);
                return 0;
            }
        }
        if (message == kPackageProgressMessage) {
            std::unique_ptr<StatusPayload> payload(
                reinterpret_cast<StatusPayload*>(l_param));
            if (g_package_status) {
                SetWindowTextW(g_package_status, payload->text.c_str());
            }
            return 0;
        }
        if (message == kPackageDoneMessage) {
            std::unique_ptr<StatusPayload> payload(
                reinterpret_cast<StatusPayload*>(l_param));
            set_packages_busy(false);
            refresh_package_list();
            if (g_package_status) {
                SetWindowTextW(g_package_status, payload->text.c_str());
            }
            if (payload->failed) {
                MessageBoxW(
                    window,
                    payload->text.c_str(),
                    L"Ошибка пакета",
                    MB_ICONERROR | MB_OK);
            }
            return 0;
        }
        if (message == WM_CLOSE) {
            if (g_runtime && g_runtime->packages_busy) {
                MessageBoxW(
                    window,
                    L"Дождитесь окончания установки или удаления.",
                    L"Пакеты",
                    MB_ICONINFORMATION | MB_OK);
                return 0;
            }
            close_packages_window();
            return 0;
        }
        if (message == WM_DESTROY) {
            g_package_list = nullptr;
            g_package_install = nullptr;
            g_package_uninstall = nullptr;
            g_package_status = nullptr;
            if (g_runtime && g_runtime->packages_window == window) {
                g_runtime->packages_window = nullptr;
            }
            return 0;
        }
    } catch (const std::exception& error) {
        MessageBoxW(
            window,
            from_utf8(error.what()).c_str(),
            L"Ошибка",
            MB_ICONERROR | MB_OK);
        return 0;
    }
    return DefWindowProcW(window, message, w_param, l_param);
}

void open_packages_window(HWND parent, HINSTANCE instance) {
    if (g_runtime && g_runtime->packages_window) {
        SetForegroundWindow(g_runtime->packages_window);
        return;
    }
    HWND packages = CreateWindowW(
        L"OfflineTranslatorPackages",
        L"Пакеты моделей",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        500,
        370,
        parent,
        nullptr,
        instance,
        nullptr);
    if (!packages) {
        throw std::runtime_error("Не удалось открыть окно пакетов");
    }
    if (g_runtime) {
        g_runtime->packages_window = packages;
    }
    EnableWindow(parent, FALSE);
    ShowWindow(packages, SW_SHOW);
    UpdateWindow(packages);
}

LRESULT CALLBACK window_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param) {
    try {
        if (message == WM_CREATE) {
            create_main_controls(window);
            if (!g_smoke_mode) {
                SetTimer(window, kSelectionPollTimer, 40, nullptr);
            }
            return 0;
        }
        if (message == WM_SIZE) {
            layout_main(window);
            return 0;
        }
        if (message == WM_GETMINMAXINFO) {
            auto* info = reinterpret_cast<MINMAXINFO*>(l_param);
            info->ptMinTrackSize.x = kMinWindowWidth;
            info->ptMinTrackSize.y = kMinWindowHeight;
            return 0;
        }
        if (message == WM_EXITSIZEMOVE) {
            persist_settings(window);
            return 0;
        }
        if (message == WM_COMMAND &&
            LOWORD(w_param) == kTranslateButton &&
            HIWORD(w_param) == BN_CLICKED) {
            start_translation(window);
            return 0;
        }
        if (message == WM_COMMAND &&
            LOWORD(w_param) == kPackagesButton &&
            HIWORD(w_param) == BN_CLICKED) {
            open_packages_window(
                window,
                window_instance(window));
            return 0;
        }
        if (message == WM_COMMAND &&
            LOWORD(w_param) == kSettingsButton &&
            HIWORD(w_param) == BN_CLICKED) {
            open_settings_window(window, window_instance(window));
            return 0;
        }
        if (message == WM_COMMAND && LOWORD(w_param) == kTrayOpen) {
            restore_from_tray(window);
            return 0;
        }
        if (message == WM_COMMAND && LOWORD(w_param) == kTrayExit) {
            using offline_translator::UiCommand;
            using offline_translator::effect_for;
            using offline_translator::UiEffect;
            if (effect_for(UiCommand::tray_exit) == UiEffect::destroy_and_quit) {
                DestroyWindow(window);
            }
            return 0;
        }
        if (message == WM_COMMAND && LOWORD(w_param) == kTrayAutostart) {
            if (!g_smoke_mode) {
                toggle_app_autostart();
            }
            return 0;
        }
        if (message == WM_COMMAND &&
            (LOWORD(w_param) == kEngineCombo ||
             LOWORD(w_param) == kSourceLanguageCombo ||
             LOWORD(w_param) == kTargetLanguageCombo) &&
            HIWORD(w_param) == CBN_SELCHANGE) {
            persist_settings(window);
            if (LOWORD(w_param) == kEngineCombo) {
                set_status(
                    selected_engine() == offline_translator::EngineKind::nllb
                        ? L"Выбран NLLB-200. Модель загрузится при переводе."
                        : L"Выбран Argos. Пакет загрузится при переводе.");
            }
            return 0;
        }
        if (message == kStatusMessage) {
            std::unique_ptr<StatusPayload> payload(
                reinterpret_cast<StatusPayload*>(l_param));
            set_status(payload->text);
            return 0;
        }
        if (message == kTranslateMessage) {
            std::unique_ptr<StatusPayload> result(
                reinterpret_cast<StatusPayload*>(l_param));
            SetWindowTextW(g_result_edit, result->text.c_str());
            set_main_busy(false);
            if (result->failed) {
                set_status(L"Ошибка. Можно повторить перевод.");
            }
            return 0;
        }
        if (message == kSelectionResultMessage) {
            std::unique_ptr<StatusPayload> result(
                reinterpret_cast<StatusPayload*>(l_param));
            const auto direction = offline_translator::choose_selection_direction(
                to_utf8(g_selection.selected_text));
            show_result_popup(
                window,
                result->text,
                direction.first,
                direction.second);
            if (result->failed) {
                set_status(L"Ошибка перевода выделения");
            }
            return 0;
        }
        if (message == kTrayMessage) {
            if (l_param == WM_LBUTTONDBLCLK || l_param == WM_LBUTTONUP) {
                restore_from_tray(window);
                return 0;
            }
            if (l_param == WM_RBUTTONUP || l_param == WM_CONTEXTMENU) {
                show_tray_menu(window);
                return 0;
            }
            return 0;
        }
        if (message == WM_TIMER && w_param == kSelectionPollTimer) {
            poll_selection(window);
            return 0;
        }
        if (message == WM_TIMER && w_param == kSelectionButtonHideTimer) {
            hide_selection_button();
            return 0;
        }
        if (message == WM_HOTKEY &&
            w_param == static_cast<WPARAM>(kShowWindowHotkey)) {
            handle_translate_hotkey(window);
            return 0;
        }
        if (message == WM_CLOSE) {
            using offline_translator::UiCommand;
            using offline_translator::effect_for;
            using offline_translator::UiEffect;
            if (effect_for(UiCommand::window_close) == UiEffect::hide_to_tray) {
                hide_to_tray(window);
                return 0;
            }
            DestroyWindow(window);
            return 0;
        }
        if (message == WM_DESTROY) {
            persist_settings(window);
            KillTimer(window, kSelectionPollTimer);
            KillTimer(window, kSelectionButtonHideTimer);
            destroy_popup_windows();
            remove_tray_icon();
            if (g_tray_icon) {
                DestroyIcon(g_tray_icon);
                g_tray_icon = nullptr;
            }
            if (g_runtime) {
                g_runtime->closing = true;
                if (g_runtime->packages_window) {
                    DestroyWindow(g_runtime->packages_window);
                    g_runtime->packages_window = nullptr;
                }
                if (g_runtime->settings_window) {
                    DestroyWindow(g_runtime->settings_window);
                    g_runtime->settings_window = nullptr;
                }
            }
            UnregisterHotKey(window, kShowWindowHotkey);
            PostQuitMessage(0);
            return 0;
        }
    } catch (const std::exception& error) {
        MessageBoxW(
            window,
            from_utf8(error.what()).c_str(),
            L"Ошибка",
            MB_ICONERROR | MB_OK);
        if (g_runtime) {
            g_runtime->busy = false;
        }
        set_main_busy(false);
        return 0;
    }
    return DefWindowProcW(window, message, w_param, l_param);
}

bool command_has_flag(const wchar_t* command_line, const wchar_t* flag) {
    return command_line != nullptr && wcsstr(command_line, flag) != nullptr;
}

int run_smoke_loop(HWND window) {
    using offline_translator::smoke_hides_forever;
    using offline_translator::smoke_may_enable_autostart;
    if (smoke_may_enable_autostart() || smoke_hides_forever()) {
        return 1;
    }
    ShowWindow(window, SW_SHOWNA);
    MSG message{};
    SendMessageW(window, WM_CLOSE, 0, 0);
    if (!IsWindow(window)) {
        return 1;
    }
    if (IsWindowVisible(window)) {
        return 1;
    }
    for (int step = 0; step < 30; ++step) {
        while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) {
            if (message.message == WM_QUIT) {
                return static_cast<int>(message.wParam);
            }
            TranslateMessage(&message);
            DispatchMessageW(&message);
        }
        Sleep(10);
    }
    if (!g_engine_combo || !g_source_language_combo ||
        !g_target_language_combo || !g_translate_button ||
        !g_packages_button || !g_settings_button) {
        return 1;
    }
    DestroyWindow(window);
    while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) {
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    if (IsWindow(window)) {
        return 1;
    }
    return 0;
}

}  // анонимное пространство имён

int WINAPI wWinMain(
    HINSTANCE instance,
    HINSTANCE,
    PWSTR command_line,
    int show_command) {
    g_smoke_mode = command_has_flag(command_line, L"--smoke-start") ||
        command_has_flag(GetCommandLineW(), L"--smoke-start");
    g_start_minimized =
        !g_smoke_mode &&
        (command_has_flag(command_line, L"--minimized") ||
         command_has_flag(GetCommandLineW(), L"--minimized"));
    g_runtime = std::make_shared<GuiRuntime>();

    const wchar_t class_name[] = L"OfflineTranslatorWindow";
    WNDCLASSW window_class{};
    window_class.hInstance = instance;
    window_class.lpfnWndProc = window_proc;
    window_class.lpszClassName = class_name;
    window_class.hCursor = LoadCursorW(
        nullptr,
        MAKEINTRESOURCEW(IDC_ARROW));
    window_class.hbrBackground = reinterpret_cast<HBRUSH>(
        COLOR_WINDOW + 1);
    if (!RegisterClassW(&window_class)) {
        return 1;
    }

    WNDCLASSW packages_class{};
    packages_class.hInstance = instance;
    packages_class.lpfnWndProc = packages_proc;
    packages_class.lpszClassName = L"OfflineTranslatorPackages";
    packages_class.hCursor = LoadCursorW(
        nullptr,
        MAKEINTRESOURCEW(IDC_ARROW));
    packages_class.hbrBackground = reinterpret_cast<HBRUSH>(
        COLOR_WINDOW + 1);
    if (!RegisterClassW(&packages_class)) {
        return 1;
    }

    WNDCLASSW settings_class{};
    settings_class.hInstance = instance;
    settings_class.lpfnWndProc = settings_proc;
    settings_class.lpszClassName = L"OfflineTranslatorSettings";
    settings_class.hCursor = LoadCursorW(
        nullptr,
        MAKEINTRESOURCEW(IDC_ARROW));
    settings_class.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    if (!RegisterClassW(&settings_class)) {
        return 1;
    }

    WNDCLASSW selection_class{};
    selection_class.hInstance = instance;
    selection_class.lpfnWndProc = selection_button_proc;
    selection_class.lpszClassName = L"OfflineTranslatorSelectionButton";
    selection_class.hCursor = LoadCursorW(
        nullptr,
        MAKEINTRESOURCEW(IDC_HAND));
    selection_class.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    if (!RegisterClassW(&selection_class)) {
        return 1;
    }

    WNDCLASSW result_class{};
    result_class.hInstance = instance;
    result_class.lpfnWndProc = result_popup_proc;
    result_class.lpszClassName = L"OfflineTranslatorResultPopup";
    result_class.hCursor = LoadCursorW(
        nullptr,
        MAKEINTRESOURCEW(IDC_ARROW));
    result_class.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    if (!RegisterClassW(&result_class)) {
        return 1;
    }

    const auto settings = offline_translator::load_settings();
    const int width = settings.window_width >= kMinWindowWidth
        ? settings.window_width
        : kDefaultWindowWidth;
    const int height = settings.window_height >= kMinWindowHeight
        ? settings.window_height
        : kDefaultWindowHeight;

    HWND window = CreateWindowW(
        class_name,
        L"Offline Translator C++",
        WS_OVERLAPPEDWINDOW,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        width,
        height,
        nullptr,
        nullptr,
        instance,
        nullptr);
    if (!window) {
        return 1;
    }
    g_runtime->main_window = window;
    g_runtime->settings = settings;
    if (!g_smoke_mode &&
        !register_translate_hotkey(window, settings.translate_hotkey)) {
        const std::wstring warning =
            L"Не удалось зарегистрировать горячую клавишу " +
            from_utf8(settings.translate_hotkey) + L".";
        MessageBoxW(
            window,
            warning.c_str(),
            L"Предупреждение",
            MB_ICONWARNING | MB_OK);
    }
    if (g_smoke_mode) {
        return run_smoke_loop(window);
    }
    add_tray_icon(window);
    if (g_start_minimized) {
        hide_to_tray(window);
    } else {
        ShowWindow(window, show_command);
        UpdateWindow(window);
    }

    MSG message{};
    while (GetMessageW(&message, nullptr, 0, 0) > 0) {
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    return static_cast<int>(message.wParam);
}
