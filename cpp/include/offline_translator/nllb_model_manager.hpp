#pragma once

#include <filesystem>
#include <string>

namespace offline_translator {

class NllbModelManager {
public:
    explicit NllbModelManager(std::filesystem::path models_root);

    std::filesystem::path model_path() const;
    bool is_installed() const;
    void validate() const;

private:
    std::filesystem::path models_root_;
};

}  // пространство имён offline_translator
