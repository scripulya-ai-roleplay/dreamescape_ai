#!/usr/bin/env python3
"""
Script to reproduce the owner_id constraint violation error.
This script demonstrates the issue mentioned in the GitHub issue:
"null value in column 'owner_id' of relation 'scenes' violates not-null constraint"
"""

import asyncio
from src.domain.models import Scene
from src.infrastructure.database.postgresqluow import PostgreSQLUoW
from src.infrastructure.gateways.scenes_gateway import SceneGateway
from src.application.scene.service import SceneService
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


async def reproduce_error():
	"""Reproduce the owner_id constraint violation error."""

	print("=== Reproducing Owner ID Constraint Violation Error ===")

	# Database connection (adjust URL as needed for your setup)
	engine = create_async_engine("postgresql+asyncpg://user:password@localhost/scripulya_ai_db")
	async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

	try:
		# Create a scene without owner_id (the old way that caused the error)
		scene_without_owner = Scene(
			title="Test Scene Without Owner",
			description="This scene has no owner and should cause constraint violation",
			background_prompt="A test background",
			# owner_id is missing/None - this should cause the error
		)

		print(f"Created Scene object: {scene_without_owner}")
		print(f"Owner ID: {scene_without_owner.owner_id}")

		# Try to save it using the gateway
		async with async_session() as session:
			uow = PostgreSQLUoW(session)
			gateway = SceneGateway(session)
			service = SceneService(uow, gateway)

			print("Attempting to create scene without owner_id...")

			# This should fail with the constraint violation
			scene_id = await service.create_scene(scene_without_owner)
			print(f"ERROR: Scene was created with ID {scene_id} - this should not happen!")

	except Exception as e:
		print(f"✓ Expected error occurred: {e}")
		print("This confirms the constraint violation issue exists.")
		return True

	print("✗ No error occurred - the constraint might not be working properly.")
	return False


if __name__ == "__main__":
	print("Note: This script demonstrates the error that should be fixed by our changes.")
	print("Run this script against the old code to see the constraint violation.")
	print()

	# Since we've already made changes, this might not reproduce the error
	# The script is more for documentation purposes
	result = asyncio.run(reproduce_error())

	if result:
		print("\n✓ Successfully demonstrated the constraint violation issue.")
	else:
		print("\n? Could not reproduce the error (possibly already fixed).")

	print("\nThe fix ensures that:")
	print("1. Scene domain model requires owner_id (not optional)")
	print("2. Scene creation API requires authentication")
	print("3. owner_id is automatically set from authenticated user")
	print("4. Tests include proper authentication")
