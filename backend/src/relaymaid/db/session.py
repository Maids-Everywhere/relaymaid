from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    Create an asynchronous SQLAlchemy session factory.

    Args:
        engine (AsyncEngine): The asynchronous SQLAlchemy engine.

    Returns:
            AsyncEngine: An instance of the asynchronous SQLAlchemy engine.
    """
    return async_sessionmaker(bind=engine, expire_on_commit=False)
