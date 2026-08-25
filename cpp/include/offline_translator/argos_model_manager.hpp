#pragma once

#include "offline_translator/package_types.hpp"

#include <filesystem>
#include <functional>
#include <string>
#include <string_view>
#include <vector>

namespace offline_translator {

class ArgosModelManager {
public:
    ArgosModelManager(
        std::filesystem::path packages_root,
        std::string source_code,
        std::string target_code);

    static std::filesystem::path default_packages_root();
    static std::vector<PackageInfo> available_packages();
    // Заглушка: удалённый индекс Argos пока не качаем, каталог — встроенные
    // пары en↔ru, совпадающие с типичной установкой Python.
    static void update_remote_index();
    static std::vector<PackageInfo> installed_packages(
        const std::filesystem::path& packages_root);

    std::filesystem::path package_path() const;
    std::filesystem::path model_path() const;
    std::filesystem::path tokenizer_path() const;
    std::filesystem::path downloads_path() const;
    bool is_installed() const;
    bool has_incomplete_package() const;
    void validate() const;

    void set_package_url(std::string url);

    void download_and_install(const ProgressCallback& progress = {});
    void install_from_staging(const ProgressCallback& progress = {});
    // unload_models выгружает движок, чтобы файлы пакета не были заняты.
    void uninstall(const std::function<void()>& unload_models = {});

private:
    std::filesystem::path find_package_dir(
        const std::filesystem::path& root) const;
    std::filesystem::path staging_package_dir() const;
    std::string package_prefix() const;
    const PackageInfo* catalog_entry() const;
    bool package_files_ready(const std::filesystem::path& package) const;

    std::filesystem::path packages_root_;
    std::string source_code_;
    std::string target_code_;
    std::string package_url_override_;
};

}  // пространство имён offline_translator
