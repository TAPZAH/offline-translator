#include "offline_translator/sentencepiece_tokenizer.hpp"

#include <sentencepiece_processor.h>

#include <stdexcept>
#include <utility>

namespace offline_translator {

class SentencePieceTokenizer::State {
public:
    explicit State(const std::string& model_path) {
        const auto status = processor.Load(model_path);
        if (!status.ok()) {
            throw std::runtime_error(
                "Не удалось загрузить SentencePiece: " + status.ToString());
        }
    }

    sentencepiece::SentencePieceProcessor processor;
};

SentencePieceTokenizer::SentencePieceTokenizer(const std::string& model_path)
    : state_(std::make_unique<State>(model_path)) {}

SentencePieceTokenizer::~SentencePieceTokenizer() = default;

std::vector<std::string> SentencePieceTokenizer::tokenize(
    std::string_view text) const {
    const auto pieces = state_->processor.EncodeAsPieces(std::string(text));
    if (pieces.empty()) {
        throw std::runtime_error("SentencePiece вернул пустые токены");
    }
    return pieces;
}

std::string SentencePieceTokenizer::detokenize(
    const std::vector<std::string>& pieces) const {
    const std::string decoded = state_->processor.DecodePieces(pieces);
    if (decoded.empty()) {
        throw std::runtime_error("SentencePiece вернул пустой текст");
    }
    return decoded;
}

}  // пространство имён offline_translator
