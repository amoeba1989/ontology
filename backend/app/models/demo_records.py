"""Small, synthetic datasets for the two isolated demonstration scenes."""
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Table
from app.database import Base

scenario = Table('demo_flight_scenarios', Base.metadata,
    Column('id', String(36), primary_key=True), Column('name', String(100), nullable=False))
aircraft = Table('demo_aircraft', Base.metadata,
    Column('id', String(36), primary_key=True), Column('name', String(100), nullable=False), Column('model', String(80)))
observation = Table('demo_flight_observations', Base.metadata,
    Column('id', String(36), primary_key=True),
    Column('aircraft_id', String(36), ForeignKey('demo_aircraft.id'), nullable=False),
    Column('scenario_id', String(36), ForeignKey('demo_flight_scenarios.id'), nullable=False),
    Column('observed_at', DateTime, nullable=False), Column('height_agl_m', Float), Column('speed_mps', Float))
customer = Table('demo_customers', Base.metadata,
    Column('id', String(36), primary_key=True), Column('name', String(100), nullable=False))
product = Table('demo_products', Base.metadata,
    Column('id', String(36), primary_key=True), Column('name', String(100), nullable=False), Column('price', Float))
order = Table('demo_orders', Base.metadata,
    Column('id', String(36), primary_key=True),
    Column('customer_id', String(36), ForeignKey('demo_customers.id'), nullable=False),
    Column('product_id', String(36), ForeignKey('demo_products.id'), nullable=False), Column('quantity', Integer))
