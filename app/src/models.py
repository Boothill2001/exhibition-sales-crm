from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import (
    Integer, Text, Numeric, Date, DateTime, ForeignKey, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    province_code: Mapped[Optional[str]] = mapped_column(Text)
    region: Mapped[Optional[str]] = mapped_column(Text)
    sales_rep: Mapped[Optional[str]] = mapped_column(Text)

    contacts: Mapped[List["Contact"]] = relationship(back_populates="company")
    opportunities: Mapped[List["Opportunity"]] = relationship(back_populates="company")
    activities: Mapped[List["Activity"]] = relationship(back_populates="company")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contact_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False)
    first_name: Mapped[Optional[str]] = mapped_column(Text)
    last_name: Mapped[Optional[str]] = mapped_column(Text)
    email: Mapped[Optional[str]] = mapped_column(Text)
    phone: Mapped[Optional[str]] = mapped_column(Text)

    company: Mapped["Company"] = relationship(back_populates="contacts")
    opportunities: Mapped[List["Opportunity"]] = relationship(back_populates="contact")


class FairEdition(Base):
    __tablename__ = "fair_editions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fair_edition_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    fair_name: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[Optional[str]] = mapped_column(Text)
    venue: Mapped[Optional[str]] = mapped_column(Text)
    starts_on: Mapped[Optional[date]] = mapped_column(Date)
    ends_on: Mapped[Optional[date]] = mapped_column(Date)
    max_stand_height_m: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))

    opportunities: Mapped[List["Opportunity"]] = relationship(back_populates="fair_edition")


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False)
    contact_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contacts.id"))
    fair_edition_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("fair_editions.id"))
    description: Mapped[Optional[str]] = mapped_column(Text)
    amount_eur: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    status: Mapped[Optional[str]] = mapped_column(Text)
    opened_on: Mapped[Optional[date]] = mapped_column(Date)
    expected_close_on: Mapped[Optional[date]] = mapped_column(Date)
    stand_area_sqm: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    client_budget_eur: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    requested_height_m: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    brief_notes: Mapped[Optional[str]] = mapped_column(Text)
    historical_campaign_code: Mapped[Optional[str]] = mapped_column(Text)

    company: Mapped["Company"] = relationship(back_populates="opportunities")
    contact: Mapped[Optional["Contact"]] = relationship(back_populates="opportunities")
    fair_edition: Mapped[Optional["FairEdition"]] = relationship(back_populates="opportunities")
    activities: Mapped[List["Activity"]] = relationship(back_populates="opportunity")
    handoff_runs: Mapped[List["HandoffRun"]] = relationship(back_populates="opportunity")


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False)
    opportunity_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("opportunities.id"))
    activity_type: Mapped[Optional[str]] = mapped_column(Text)
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    details: Mapped[Optional[str]] = mapped_column(Text)
    follow_up_on: Mapped[Optional[date]] = mapped_column(Date)
    completion_marker: Mapped[Optional[str]] = mapped_column(Text)
    legacy_author: Mapped[Optional[str]] = mapped_column(Text)

    company: Mapped["Company"] = relationship(back_populates="activities")
    opportunity: Mapped[Optional["Opportunity"]] = relationship(back_populates="activities")


class HandoffRun(Base):
    __tablename__ = "handoff_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(Integer, ForeignKey("opportunities.id"), nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()")
    )
    crm_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)
    preparer_output: Mapped[Optional[dict]] = mapped_column(JSONB)
    checker_output: Mapped[Optional[dict]] = mapped_column(JSONB)
    coordinator_decision: Mapped[Optional[str]] = mapped_column(Text)
    decision_reason: Mapped[Optional[str]] = mapped_column(Text)

    opportunity: Mapped["Opportunity"] = relationship(back_populates="handoff_runs")
