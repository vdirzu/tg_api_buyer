from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def make_database(url: str):
    engine = create_async_engine(url, pool_pre_ping=True, hide_parameters=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)
