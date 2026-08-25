#pragma once

#include "offline_translator/translation_engine.hpp"

#include <filesystem>
#include <memory>
#include <string>
#include <string_view>

namespace offline_translator {

enum class EngineKind {
    argos,
    nllb,
};

class TranslationApplication {
public:
    TranslationApplication(
        EngineKind engine_kind,
        std::filesystem::path models_root);
    ~TranslationApplication();

    TranslationApplication(const TranslationApplication&) = delete;
    TranslationApplication& operator=(const TranslationApplication&) = delete;

    TranslationResult translate(
        std::string_view text,
        std::string_view source_code,
        std::string_view target_code);
    void warmup(std::string_view source_code, std::string_view target_code);
    void invalidate();
    void stop();

    static std::string engine_name(EngineKind engine_kind);

private:
    class State;
    std::unique_ptr<State> state_;
};

}  // пространство имён offline_translator
