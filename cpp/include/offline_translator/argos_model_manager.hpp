#pragma once

#include <filesystem>
#include <string>
#include <string_view>

namespace offline_translator {

class ArgosModelManager {
public:
    ArgosModelManager(
        std::filesystem::path packages_root,
        std::string source_code,
        std::string target_code);

    std::filesystem::path package_path() const;
    std::filesystem::path model_path() const;
    std::filesystem::path tokenizer_path() const;
    bool is_installed() const;
    void validate() const;

private:
    std::filesystem::path packages_root_;
    std::string source_code_;
    std::string target_code_;
};

}  // пространство имён offline_translator
