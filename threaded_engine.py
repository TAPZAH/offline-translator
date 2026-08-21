import queue
import threading


class ThreadedEngine:
    """Общий рабочий поток для движков, которые нельзя вызывать из UI."""

    def __init__(self, thread_name: str) -> None:
        self._requests: queue.Queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._run_worker,
            name=thread_name,
            daemon=True,
        )
        self._thread.start()

    def translate(self, text: str, source_code: str, target_code: str) -> str:
        """Переводит текст и возвращает только итоговую строку."""
        return self.translate_result(text, source_code, target_code).text

    def translate_result(self, text: str, source_code: str, target_code: str):
        """Переводит текст в рабочем потоке."""
        return self._call("translate", text, source_code, target_code)

    def warmup(self, source_code: str, target_code: str) -> None:
        """Загружает модель заранее, чтобы первая кнопка не тормозила."""
        self._call("warmup", source_code, target_code)

    def invalidate(self) -> None:
        """Сбрасывает кэш моделей после установки пакетов."""
        self._call("invalidate")

    def has_translation_path(self, source_code: str, target_code: str) -> bool:
        """Проверяет, есть ли прямой или двойной маршрут перевода."""
        return self.translation_route(source_code, target_code) is not None

    def translation_route(self, source_code: str, target_code: str) -> str | None:
        """Возвращает 'direct', 'en' или None, если пути нет."""
        raise NotImplementedError

    def _call(self, action: str, *args):
        """Отправляет задачу в рабочий поток и ждёт ответ."""
        reply: queue.Queue = queue.Queue(maxsize=1)
        self._requests.put((action, args, reply))
        result = reply.get()
        if isinstance(result, Exception):
            raise result
        return result

    def _run_worker(self) -> None:
        """Обрабатывает перевод в одном потоке."""
        state = self._create_state()
        while True:
            action, args, reply = self._requests.get()
            try:
                if action == "invalidate":
                    self._worker_invalidate(state)
                    reply.put(None)
                elif action == "warmup":
                    self._worker_warmup(state, *args)
                    reply.put(None)
                elif action == "translate":
                    reply.put(self._worker_translate(state, *args))
                else:
                    reply.put(RuntimeError(f"Неизвестное действие: {action}"))
            except Exception as error:
                reply.put(error)

    def _create_state(self):
        """Состояние, которое живёт только в рабочем потоке."""
        return None

    def _worker_invalidate(self, state) -> None:
        """Сбрасывает загруженные модели в рабочем потоке."""
        return None

    def _worker_warmup(self, state, source_code: str, target_code: str) -> None:
        """Прогревает модель пробным переводом; ошибка не пробрасывается."""
        try:
            self._worker_translate(state, "Hello", source_code, target_code)
        except Exception:
            pass

    def _worker_translate(self, state, text: str, source_code: str, target_code: str):
        """Выполняет перевод в рабочем потоке."""
        raise NotImplementedError
