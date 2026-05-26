# Owner A — backend/app/repositories/base.py
#
# Single import point for TenantRepository so all concrete repos use one path.
# Keeps Owner B, C, D's repos clean: from app.repositories.base import TenantRepository

from app.tenancy.repository import TenantRepository

__all__ = ["TenantRepository"]
