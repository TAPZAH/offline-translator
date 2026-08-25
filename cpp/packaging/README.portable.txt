Оффлайн Переводчик — портативная сборка C++ (Win32)

Распакуйте папку куда удобно и запустите offline_translator_win32.exe.
Нужны Windows 10 или 11, 64-bit. Отдельно ставить Visual C++ Redistributable
не требуется: vcruntime/msvcp/vcomp лежат рядом с exe.

{{MODELS}}

Не удаляйте папки assets, data и licenses.
Настройки пишутся в data\settings.json (портативный режим).
Если вы раньше пользовались Python-версией, установщик может скопировать
settings.json из профиля; в zip-поставке этого нет, пока не указан -MigrateSettings.

Автозагрузка включается только в «Настройки...» (не при установке).

Лицензии сторонних библиотек: licenses\THIRD_PARTY.md
