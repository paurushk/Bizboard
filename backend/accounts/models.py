from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel
from core.validators import validate_gstin


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    full_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class Company(TimeStampedModel):
    """Single company per tenant (single warehouse) — MVP lock."""

    class RegistrationType(models.TextChoices):
        REGULAR = "REGULAR"
        COMPOSITION = "COMPOSITION"
        UNREGISTERED = "UNREGISTERED"

    class NegativeStockPolicy(models.TextChoices):
        BLOCK = "BLOCK"
        WARN = "WARN"

    name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255, blank=True)
    gstin = models.CharField(max_length=15, blank=True, validators=[validate_gstin])
    registration_type = models.CharField(
        max_length=16, choices=RegistrationType.choices, default=RegistrationType.REGULAR
    )
    state = models.CharField(max_length=64, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    upi_id = models.CharField(max_length=100, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account = models.CharField(max_length=32, blank=True)
    bank_ifsc = models.CharField(max_length=16, blank=True)
    logo = models.ForeignKey(
        "core.FileAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    fy_start_month = models.PositiveSmallIntegerField(default=4)
    negative_stock_policy = models.CharField(
        max_length=8, choices=NegativeStockPolicy.choices, default=NegativeStockPolicy.BLOCK
    )
    invoice_terms = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name

    @property
    def is_gst_registered(self):
        return self.registration_type != self.RegistrationType.UNREGISTERED and bool(self.gstin)


class CompanyUser(TimeStampedModel):
    """RBAC membership — Owner/Admin or Sales Staff with permission flags (E0.8)."""

    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner/Admin"
        SALES_STAFF = "SALES_STAFF", "Sales Staff"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="company_memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.SALES_STAFF)
    can_manage_inventory = models.BooleanField(default=False)
    can_import = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("company", "user")]

    def __str__(self):
        return f"{self.user} @ {self.company} ({self.role})"


class OtpChallenge(TimeStampedModel):
    phone = models.CharField(max_length=20, db_index=True)
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    consumed = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at
