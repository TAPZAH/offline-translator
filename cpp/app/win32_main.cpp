#include "offline_translator/translation_application.hpp"

#include <windows.h>

#include <array>
#include <exception>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>

namespace {

constexpr UINT kTranslateMessage = WM_APP + 1;
constexpr int kEngineCombo = 1001;
constexpr int kSourceEdit = 1002;
constexpr int kTranslateButton = 1003;
constexpr int kResultEdit = 1004;
constexpr int kSourceLanguageCombo = 1005;
constexpr int kTargetLanguageCombo = 1006;
constexpr int kShowWindowHotkey = 2001;

HWND g_engine_combo = nullptr;
HWND g_source_edit = nullptr;
HWND g_translate_button = nullptr;
HWND g_result_edit = nullptr;
HWND g_source_language_combo = nullptr;
HWND g_target_language_combo = nullptr;

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

struct TranslationMessage {
    std::wstring text;
    bool failed{false};
};

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

std::wstring clipboard_text() {
    if (!OpenClipboard(nullptr)) {
        throw std::runtime_error("Не удалось открыть буфер обмена");
    }
    struct ClipboardGuard {
        ~ClipboardGuard() {
            CloseClipboard();
        }
    } clipboard_guard;
    HGLOBAL handle = GetClipboardData(CF_UNICODETEXT);
    if (!handle) {
        return {};
    }
    const auto* data = static_cast<const wchar_t*>(GlobalLock(handle));
    if (!data) {
        throw std::runtime_error("Не удалось прочитать буфер обмена");
    }
    const std::wstring result(data);
    GlobalUnlock(handle);
    return result;
}

std::string selected_language(HWND combo) {
    const LRESULT index = SendMessageW(combo, CB_GETCURSEL, 0, 0);
    if (index < 0 || index >= static_cast<LRESULT>(std::size(kLanguages))) {
        throw std::runtime_error("Не выбран язык");
    }
    return kLanguages[static_cast<std::size_t>(index)].code;
}

void refresh_language_combos() {
    // Показываем каталог языков моделей, а не только установленные пакеты.
    const std::size_t count = std::size(kLanguages);
    SendMessageW(g_source_language_combo, CB_RESETCONTENT, 0, 0);
    SendMessageW(g_target_language_combo, CB_RESETCONTENT, 0, 0);
    for (std::size_t index = 0; index < count; ++index) {
        SendMessageW(
            g_source_language_combo,
            CB_ADDSTRING,
            0,
            reinterpret_cast<LPARAM>(kLanguages[index].name));
        SendMessageW(
            g_target_language_combo,
            CB_ADDSTRING,
            0,
            reinterpret_cast<LPARAM>(kLanguages[index].name));
    }
    SendMessageW(g_source_language_combo, CB_SETCURSEL, 0, 0);
    SendMessageW(
        g_target_language_combo,
        CB_SETCURSEL,
        count > 1 ? 1 : 0,
        0);
}

void start_translation(HWND window) {
    const std::wstring source_text = control_text(g_source_edit);
    const bool use_nllb =
        SendMessageW(g_engine_combo, CB_GETCURSEL, 0, 0) == 1;
    const auto engine_kind = use_nllb
        ? offline_translator::EngineKind::nllb
        : offline_translator::EngineKind::argos;
    const std::string source_language = selected_language(
        g_source_language_combo);
    const std::string target_language = selected_language(
        g_target_language_combo);
    const std::string text = to_utf8(source_text);
    const std::wstring root = model_root(use_nllb);

    EnableWindow(g_translate_button, FALSE);
    SetWindowTextW(g_result_edit, L"Перевод выполняется...");
    std::thread(
        [window, text, root, engine_kind, source_language, target_language]() {
            auto result = std::make_unique<TranslationMessage>();
            try {
                offline_translator::TranslationApplication application(
                    engine_kind,
                    to_utf8(root));
                result->text = from_utf8(
                    application.translate(
                        text,
                        source_language,
                        target_language)
                        .text);
            } catch (const std::exception& error) {
                result->failed = true;
                result->text = from_utf8(error.what());
            }
            PostMessageW(
                window,
                kTranslateMessage,
                0,
                reinterpret_cast<LPARAM>(result.release()));
        })
        .detach();
}

LRESULT CALLBACK window_proc(
    HWND window,
    UINT message,
    WPARAM w_param,
    LPARAM l_param) {
    try {
        if (message == WM_CREATE) {
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
                WS_VISIBLE | WS_CHILD | CBS_DROPDOWNLIST,
                90,
                12,
                180,
                160,
                window,
                reinterpret_cast<HMENU>(static_cast<INT_PTR>(kEngineCombo)),
                nullptr,
                nullptr);
            SendMessageW(g_engine_combo, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"Argos"));
            SendMessageW(g_engine_combo, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"NLLB-200"));
            SendMessageW(g_engine_combo, CB_SETCURSEL, 0, 0);
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
                WS_VISIBLE | WS_CHILD | CBS_DROPDOWNLIST,
                90,
                48,
                150,
                140,
                window,
                reinterpret_cast<HMENU>(
                    static_cast<INT_PTR>(kSourceLanguageCombo)),
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
                WS_VISIBLE | WS_CHILD | CBS_DROPDOWNLIST,
                335,
                48,
                130,
                140,
                window,
                reinterpret_cast<HMENU>(
                    static_cast<INT_PTR>(kTargetLanguageCombo)),
                nullptr,
                nullptr);
            refresh_language_combos();
            g_source_edit = CreateWindowW(
                L"EDIT",
                L"Hello world",
                WS_VISIBLE | WS_CHILD | WS_BORDER | ES_MULTILINE,
                16,
                84,
                440,
                90,
                window,
                reinterpret_cast<HMENU>(static_cast<INT_PTR>(kSourceEdit)),
                nullptr,
                nullptr);
            g_translate_button = CreateWindowW(
                L"BUTTON",
                L"Перевести",
                WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
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
                WS_VISIBLE | WS_CHILD | WS_BORDER | ES_MULTILINE |
                    ES_READONLY,
                16,
                228,
                440,
                110,
                window,
                reinterpret_cast<HMENU>(static_cast<INT_PTR>(kResultEdit)),
                nullptr,
                nullptr);
            return 0;
        }
        if (message == WM_COMMAND &&
            LOWORD(w_param) == kTranslateButton &&
            HIWORD(w_param) == BN_CLICKED) {
            start_translation(window);
            return 0;
        }
        if (message == WM_COMMAND &&
            LOWORD(w_param) == kEngineCombo &&
            HIWORD(w_param) == CBN_SELCHANGE) {
            refresh_language_combos();
            return 0;
        }
        if (message == kTranslateMessage) {
            std::unique_ptr<TranslationMessage> result(
                reinterpret_cast<TranslationMessage*>(l_param));
            SetWindowTextW(g_result_edit, result->text.c_str());
            EnableWindow(g_translate_button, TRUE);
            return 0;
        }
        if (message == WM_HOTKEY &&
            w_param == static_cast<WPARAM>(kShowWindowHotkey)) {
            const std::wstring copied_text = clipboard_text();
            if (!copied_text.empty()) {
                SetWindowTextW(g_source_edit, copied_text.c_str());
                start_translation(window);
            }
            ShowWindow(window, SW_SHOWNORMAL);
            SetForegroundWindow(window);
            SetFocus(g_source_edit);
            return 0;
        }
        if (message == WM_DESTROY) {
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
        return 0;
    }
    return DefWindowProcW(window, message, w_param, l_param);
}

}  // анонимное пространство имён

int WINAPI wWinMain(
    HINSTANCE instance,
    HINSTANCE,
    PWSTR,
    int show_command) {
    const wchar_t class_name[] = L"OfflineTranslatorWindow";
    WNDCLASSW window_class{};
    window_class.hInstance = instance;
    window_class.lpfnWndProc = window_proc;
    window_class.lpszClassName = class_name;
    window_class.hCursor = LoadCursorW(
        nullptr,
        MAKEINTRESOURCEW(IDC_ARROW));
    if (!RegisterClassW(&window_class)) {
        return 1;
    }

    HWND window = CreateWindowW(
        class_name,
        L"Offline Translator C++",
        WS_OVERLAPPEDWINDOW,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        500,
        390,
        nullptr,
        nullptr,
        instance,
        nullptr);
    if (!window) {
        return 1;
    }
    if (!RegisterHotKey(
            window,
            kShowWindowHotkey,
            MOD_CONTROL | MOD_SHIFT,
            'T')) {
        MessageBoxW(
            window,
            L"Не удалось зарегистрировать Ctrl+Shift+T.",
            L"Предупреждение",
            MB_ICONWARNING | MB_OK);
    }
    ShowWindow(window, show_command);
    UpdateWindow(window);

    MSG message{};
    while (GetMessageW(&message, nullptr, 0, 0) > 0) {
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    return static_cast<int>(message.wParam);
}
