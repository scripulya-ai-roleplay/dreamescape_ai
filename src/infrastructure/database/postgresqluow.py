from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.common import IUnitOfWork


class PostgresqlUOW(IUnitOfWork):
	def __init__(self, session: AsyncSession):
		self.session = session

	async def __aenter__(self):
		return self

	async def __aexit__(self, exc_type, exc_val, exc_tb):
		if exc_type is not None:
			await self.session.rollback()
		else:
			await self.session.commit()

	async def commit(self):
		await self.session.commit()

	async def rollback(self):
		await self.session.rollback()
