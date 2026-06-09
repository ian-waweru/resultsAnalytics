from django.contrib.auth.models import BaseUserManager
from django.db import models


class TeacherManager(BaseUserManager):
    """
    Custom user manager for the Teacher model.

    Handles user creation for `manage.py createsuperuser`, programmatic
    user creation, and provides domain-specific querysets for school workflows.
    """

    # ------------------------------------------------------------------
    # Querysets
    # ------------------------------------------------------------------

    def get_by_natural_key(self, username):
        """
        Enables natural key lookups during deserialization and authentication,
        ensuring uniform NFC normalization across usernames.
        """
        return self.get(username=self.model.normalize_username(username))

    def hods(self):
        """Return all active teachers with HOD designation."""
        return self.get_queryset().filter(is_hod=True, is_active=True)

    def tsc_teachers(self):
        """Return all TSC (government-employed) teachers."""
        return self.get_queryset().filter(
            tsc_number__isnull=False, is_active=True
        ).exclude(tsc_number="")

    def bom_teachers(self):
        """
        Return all Board of Management (BOM) employed teachers.
        BOM teachers have an empty or null TSC number.
        """
        return self.get_queryset().filter(is_active=True).filter(
            models.Q(tsc_number__isnull=True) | models.Q(tsc_number="")
        )

    # ------------------------------------------------------------------
    # User creation
    # ------------------------------------------------------------------

    def create_user(self, username, email=None, password=None, **extra_fields):
        """Creates and saves a regular Teacher with the given credentials."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_hod", False)
        return self._create_teacher(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        """
        Creates and saves a superuser.
        Superusers default to HOD status since they need full management access.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_hod", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_teacher(username, email, password, **extra_fields)

    def _create_teacher(self, username, email, password, **extra_fields):
        """
        Core creation helper shared by create_user and create_superuser.

        Differences from a naive implementation:
        - Calls normalize_username() so Unicode usernames are NFC-normalised,
          matching the behaviour of AbstractBaseUser's own manager.
        - Ensures full_name is never left blank (falls back to username so
          __str__ and admin display are never broken).
        - Normalises email to lowercase domain per RFC 5321.
        """
        if not username:
            raise ValueError("A username must be provided.")

        # normalize username (NFC Unicode normalisation) — Django's own
        # AbstractBaseUser._create_user does this; skipping it causes subtle
        # lookup mismatches for non-ASCII usernames.
        username = self.model.normalize_username(username)

        # ensure full_name is always populated so __str__ never returns
        # an empty string. Callers can pass full_name= explicitly; otherwise
        # we fall back to the username as a safe default.
        if not extra_fields.get("full_name"):
            extra_fields["full_name"] = username

        # normalize_email handles None gracefully (returns ""), but being
        # explicit about the empty-string case keeps behaviour predictable.
        email = self.normalize_email(email) if email else ""

        teacher = self.model(username=username, email=email, **extra_fields)
        teacher.set_password(password)
        teacher.save(using=self._db)
        return teacher