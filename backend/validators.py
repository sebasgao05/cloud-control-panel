"""
Cloud Control Panel - Pydantic request validation models.
All POST/PUT endpoints validate request bodies using these models.
"""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# --- Reusable patterns ---
ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
AWS_INSTANCE_ID_PATTERN = re.compile(r"^i-[a-f0-9]{8,17}$")
AWS_ROLE_ARN_PATTERN = re.compile(r"^arn:aws:iam::\d{12}:role/.+$")
AWS_REGION_PATTERN = re.compile(r"^[a-z]{2}-[a-z]+-\d$")
RDS_RESOURCE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]*$")
LIGHTSAIL_RESOURCE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.\-]*$")
HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
CRON_PATTERN = re.compile(r"^[0-9*,/-]+\s+[0-9*,/-]+\s+[0-9*,/-]+\s+[0-9*,/-]+\s+[0-9*,/-]+$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_id(value: str, field_name: str = "id") -> str:
    """Validate an ID field: alphanumeric + hyphens/underscores, 1-50 chars."""
    if not value or len(value) > 50:
        raise ValueError(f"{field_name} must be 1-50 characters")
    if not ID_PATTERN.match(value):
        raise ValueError(
            f"{field_name} must start with alphanumeric and contain only alphanumeric, hyphens, or underscores"
        )
    return value


def validate_path_parameter(value: str) -> bool:
    """Validate a path parameter: non-empty, alphanumeric + hyphens/underscores, max 50 chars."""
    if not value or len(value) > 50:
        return False
    return bool(ID_PATTERN.match(value))


# --- Account models ---


class CreateAccountRequest(BaseModel):
    """Validation model for POST /api/accounts."""

    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    awsAccountId: str | None = Field(default=None, max_length=12)
    region: str = Field(default="us-east-1", max_length=20)
    crossAccountRoleArn: str | None = Field(default=None, max_length=200)
    features: dict[str, Any] | None = None

    @field_validator("id")
    @classmethod
    def validate_account_id(cls, v: str) -> str:
        return validate_id(v, "id")

    @field_validator("region")
    @classmethod
    def validate_region(cls, v: str) -> str:
        if v and not AWS_REGION_PATTERN.match(v):
            raise ValueError("region must match format like us-east-1")
        return v

    @field_validator("crossAccountRoleArn")
    @classmethod
    def validate_role_arn(cls, v: str | None) -> str | None:
        if v and not AWS_ROLE_ARN_PATTERN.match(v):
            raise ValueError("crossAccountRoleArn must be a valid AWS IAM role ARN")
        return v

    @field_validator("awsAccountId")
    @classmethod
    def validate_aws_account_id(cls, v: str | None) -> str | None:
        if v and not re.match(r"^\d{12}$", v):
            raise ValueError("awsAccountId must be a 12-digit AWS account ID")
        return v


# --- Instance models ---


class CreateInstanceRequest(BaseModel):
    """Validation model for POST /api/accounts/{id}/instances."""

    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    instanceId: str = Field(..., min_length=1, max_length=30)
    description: str | None = Field(default=None, max_length=1000)
    dashboardPort: int | None = Field(default=None, ge=1, le=65535)
    group: str | None = Field(default=None, max_length=50)

    @field_validator("id")
    @classmethod
    def validate_instance_id_field(cls, v: str) -> str:
        return validate_id(v, "id")

    @field_validator("instanceId")
    @classmethod
    def validate_aws_instance_id(cls, v: str) -> str:
        if not AWS_INSTANCE_ID_PATTERN.match(v):
            raise ValueError("instanceId must match pattern i-[a-f0-9]{8,17}")
        return v

    @field_validator("group")
    @classmethod
    def validate_group_ref(cls, v: str | None) -> str | None:
        if v and not ID_PATTERN.match(v):
            raise ValueError("group must be a valid ID (alphanumeric + hyphens/underscores)")
        return v


# --- Resource models (multi-service) ---

RESOURCE_TYPES = ("ec2", "rds", "ecs", "lightsail", "apprunner")


class CreateResourceRequest(BaseModel):
    """Validation model for POST /api/accounts/{id}/resources."""

    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    type: Literal["ec2", "rds", "ecs", "lightsail", "apprunner"]
    resourceId: str = Field(..., min_length=1, max_length=200)
    # Optional type-specific config
    resourceType: Literal["cluster", "instance"] | None = None  # RDS
    targetCount: int | None = Field(default=None, ge=1, le=10)  # ECS
    description: str | None = Field(default=None, max_length=1000)
    group: str | None = Field(default=None, max_length=50)

    @field_validator("id")
    @classmethod
    def validate_resource_id_field(cls, v: str) -> str:
        return validate_id(v, "id")

    @field_validator("resourceId")
    @classmethod
    def validate_resource_id_format(cls, v: str, info) -> str:
        """Validate resourceId format based on resource type."""
        # Type may not be available during individual field validation in all cases,
        # so full type-specific validation is done in the model validator below.
        return v

    @field_validator("group")
    @classmethod
    def validate_group_ref(cls, v: str | None) -> str | None:
        if v and not ID_PATTERN.match(v):
            raise ValueError("group must be a valid ID (alphanumeric + hyphens/underscores)")
        return v

    @model_validator(mode="after")
    def validate_resource_id_by_type(self) -> "CreateResourceRequest":
        """Validate resourceId format based on the resource type."""
        resource_type = self.type
        resource_id = self.resourceId

        if resource_type == "ec2":
            if not AWS_INSTANCE_ID_PATTERN.match(resource_id):
                raise ValueError("resourceId for ec2 must match pattern i-[a-f0-9]{8,17}")
        elif resource_type == "rds":
            if len(resource_id) > 63:
                raise ValueError("resourceId for rds must be 1-63 characters")
            if not RDS_RESOURCE_ID_PATTERN.match(resource_id):
                raise ValueError("resourceId for rds must contain only alphanumeric characters and hyphens")
        elif resource_type == "ecs":
            # ECS accepts ARN or cluster/service format, 1-200 chars (already enforced by Field)
            pass
        elif resource_type == "lightsail":
            if len(resource_id) > 63:
                raise ValueError("resourceId for lightsail must be 1-63 characters")
            if not LIGHTSAIL_RESOURCE_ID_PATTERN.match(resource_id):
                raise ValueError(
                    "resourceId for lightsail must contain only alphanumeric characters, hyphens, and periods"
                )
        elif resource_type == "apprunner":
            if not resource_id.startswith("arn:aws:apprunner:"):
                raise ValueError("resourceId for apprunner must start with 'arn:aws:apprunner:'")

        return self


def check_duplicate_resource_id(existing_resources: list[dict], new_resource_id: str) -> bool:
    """Check if a resource ID already exists in the account's resource list.

    Args:
        existing_resources: List of existing resource dicts in the account.
        new_resource_id: The ID of the new resource being created.

    Returns:
        True if a duplicate exists, False otherwise.
    """
    return any(r.get("id") == new_resource_id for r in existing_resources)


# --- Group models ---


class CreateGroupRequest(BaseModel):
    """Validation model for POST /api/accounts/{id}/groups."""

    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    color: str | None = Field(default=None, max_length=7)
    startOrder: list[str] = Field(default_factory=list)
    stopOrder: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_group_id(cls, v: str) -> str:
        return validate_id(v, "id")

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        if v and not HEX_COLOR_PATTERN.match(v):
            raise ValueError("color must be a valid hex color (e.g. #FF0000)")
        return v


# --- API Key models ---


class SchedulerPermissions(BaseModel):
    """Sub-model for scheduler permissions on an API key."""

    view: bool = False
    edit: bool = False


class CreateKeyRequest(BaseModel):
    """Validation model for POST /api/keys/create."""

    key: str | None = Field(default=None, max_length=200)
    name: str = Field(..., min_length=1, max_length=100)
    role: Literal["operator", "admin"] = "operator"
    accounts: list[str] = Field(default_factory=list)
    scheduler: SchedulerPermissions | None = None

    @field_validator("accounts")
    @classmethod
    def validate_accounts_list(cls, v: list[str]) -> list[str]:
        for acc_id in v:
            if acc_id != "*" and not ID_PATTERN.match(acc_id):
                raise ValueError(f"Invalid account ID in accounts list: {acc_id}")
        return v


class UpdateKeyAccountsRequest(BaseModel):
    """Validation model for PUT /api/keys/{id}/accounts."""

    accounts: list[str] = Field(default_factory=list)

    @field_validator("accounts")
    @classmethod
    def validate_accounts_list(cls, v: list[str]) -> list[str]:
        for acc_id in v:
            if acc_id != "*" and not ID_PATTERN.match(acc_id):
                raise ValueError(f"Invalid account ID in accounts list: {acc_id}")
        return v


# --- Schedule models ---


class ScheduleRule(BaseModel):
    """A single schedule rule."""

    id: str | None = Field(default=None, max_length=50)
    name: str | None = Field(default=None, max_length=100)
    startCron: str | None = Field(default=None, max_length=50)
    stopCron: str | None = Field(default=None, max_length=50)
    instances: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("startCron", "stopCron")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        if v and not CRON_PATTERN.match(v.strip()):
            raise ValueError("cron expression must have 5 space-separated fields")
        return v


class UpdateScheduleRequest(BaseModel):
    """Validation model for PUT /api/accounts/{id}/schedule."""

    rules: list[ScheduleRule] = Field(default_factory=list)
    timezone: str | None = Field(default=None, max_length=50)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v and len(v) < 2:
            raise ValueError("timezone must be a valid timezone string")
        return v


# --- Notification models ---


class NotificationChannelConfig(BaseModel):
    """Configuration for a notification channel."""

    # Email fields
    to: str | None = Field(default=None, max_length=200)
    smtpHost: str | None = Field(default=None, max_length=200)
    smtpPort: int | None = Field(default=None, ge=1, le=65535)
    smtpUser: str | None = Field(default=None, max_length=200)
    smtpPass: str | None = Field(default=None, max_length=200)
    # Telegram fields
    botToken: str | None = Field(default=None, max_length=200)
    chatId: str | None = Field(default=None, max_length=50)
    # Teams fields
    webhookUrl: str | None = Field(default=None, max_length=500)

    model_config = {"extra": "allow"}

    @field_validator("to")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v and not EMAIL_PATTERN.match(v):
            raise ValueError("to must be a valid email address")
        return v

    @field_validator("webhookUrl")
    @classmethod
    def validate_webhook_url(cls, v: str | None) -> str | None:
        if v and not v.startswith("https://"):
            raise ValueError("webhookUrl must start with https://")
        return v


class NotificationChannel(BaseModel):
    """A notification channel."""

    id: str | None = Field(default=None, max_length=50)
    name: str | None = Field(default=None, max_length=100)
    type: str | None = Field(default=None, max_length=20)
    enabled: bool | None = None
    events: list[str] = Field(default_factory=list)
    config: NotificationChannelConfig | None = None

    model_config = {"extra": "allow"}


class UpdateNotificationsRequest(BaseModel):
    """Validation model for PUT /api/accounts/{id}/notifications."""

    channels: list[NotificationChannel] = Field(default_factory=list)


# --- Config import model ---


class ImportConfigRequest(BaseModel):
    """Validation model for PUT /api/config."""

    settings: dict[str, Any] | None = None
    apiKeys: dict[str, Any] | None = None
    accounts: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"extra": "allow"}


# --- Test notification model ---


class TestNotificationRequest(BaseModel):
    """Validation model for POST /api/accounts/{id}/notifications/test."""

    channelId: str = Field(..., min_length=1, max_length=50)


# --- Helper for formatting validation errors ---


def format_validation_errors(exc) -> list[dict[str, Any]]:
    """Format pydantic ValidationError into a list of error details."""
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )
    return errors
