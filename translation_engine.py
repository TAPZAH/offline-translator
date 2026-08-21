from app_settings import ENGINE_ARGOS, get_engine_name


def get_engine():
    """Возвращает движок, выбранный в настройках."""
    if get_engine_name() == ENGINE_ARGOS:
        from argos_engine import get_engine as get_argos_engine

        return get_argos_engine()
    from firefox_engine import get_engine as get_firefox_engine

    return get_firefox_engine()


def invalidate_engines() -> None:
    """Сбрасывает кэш уже созданных движков."""
    try:
        import firefox_engine

        if firefox_engine._engine is not None:
            firefox_engine._engine.invalidate()
    except Exception:
        pass
    try:
        import argos_engine

        if argos_engine._engine is not None:
            argos_engine._engine.invalidate()
    except Exception:
        pass
