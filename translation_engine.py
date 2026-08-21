from app_settings import ENGINE_ARGOS, ENGINE_NLLB, get_engine_name


def get_engine():
    """Возвращает движок, выбранный в настройках."""
    engine = get_engine_name()
    if engine == ENGINE_ARGOS:
        from argos_engine import get_engine as get_argos_engine

        return get_argos_engine()
    if engine == ENGINE_NLLB:
        from nllb_engine import get_engine as get_nllb_engine

        return get_nllb_engine()
    from firefox_engine import get_engine as get_firefox_engine

    return get_firefox_engine()


def invalidate_engines() -> None:
    """Сбрасывает кэш уже созданных движков и списков пакетов."""
    for module_name in ("firefox_engine", "argos_engine", "nllb_engine"):
        try:
            module = __import__(module_name)
            engine = getattr(module, "_engine", None)
            if engine is not None:
                engine.invalidate()
        except Exception:
            pass
    try:
        from packages import invalidate_caches

        invalidate_caches()
    except Exception:
        pass
