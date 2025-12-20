-- Generated Full Schema from SQLModel Models
-- Includes all tables and enums defined in code

BEGIN;

-- Drop existing tables and types to allow clean reset
DROP TABLE IF EXISTS annual_snapshots_liabilities CASCADE;
DROP TABLE IF EXISTS annual_snapshots_income CASCADE;
DROP TABLE IF EXISTS annual_snapshots_expenses CASCADE;
DROP TABLE IF EXISTS annual_snapshots_assets CASCADE;
DROP TABLE IF EXISTS user_milestones CASCADE;
DROP TABLE IF EXISTS security_holdings CASCADE;
DROP TABLE IF EXISTS roth_conversion_scenarios CASCADE;
DROP TABLE IF EXISTS asset_allocations CASCADE;
DROP TABLE IF EXISTS annual_snapshots CASCADE;
DROP TABLE IF EXISTS user_goals CASCADE;
DROP TABLE IF EXISTS roth_conversion_plans CASCADE;
DROP TABLE IF EXISTS retirement_plans CASCADE;
DROP TABLE IF EXISTS multi_step_form_progress CASCADE;
DROP TABLE IF EXISTS investment_accounts CASCADE;
DROP TABLE IF EXISTS activities CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS ref_milestones CASCADE;
DROP TABLE IF EXISTS ref_goals CASCADE;
DROP TABLE IF EXISTS alembic_version CASCADE;
DROP TYPE IF EXISTS goaltype CASCADE;


CREATE TYPE goaltype AS ENUM ('EMERGENCY_FUND', 'RETIREMENT_401K', 'DEBT_PAYOFF', 'MORTGAGE_PAYOFF', 'HEALTH_SAVINGS', 'ADDITIONAL_INCOME', 'CUSTOM');

CREATE TABLE users (
	first_name VARCHAR, 
	last_name VARCHAR, 
	email VARCHAR NOT NULL, 
	current_age INTEGER, 
	target_retirement_age INTEGER, 
	current_location VARCHAR, 
	marital_status VARCHAR, 
	dependents INTEGER, 
	current_income NUMERIC(12, 2), 
	desired_lifestyle VARCHAR, 
	currency VARCHAR NOT NULL, 
	has_spouse BOOLEAN NOT NULL, 
	spouse_first_name VARCHAR, 
	spouse_last_name VARCHAR, 
	spouse_current_age INTEGER, 
	spouse_target_retirement_age INTEGER, 
	spouse_current_income NUMERIC(12, 2), 
	other_income_source_1 VARCHAR, 
	other_income_amount_1 NUMERIC(12, 2), 
	other_income_source_2 VARCHAR, 
	other_income_amount_2 NUMERIC(12, 2), 
	expected_income_growth NUMERIC(5, 2), 
	spouse_expected_income_growth NUMERIC(5, 2), 
	expenses JSON, 
	total_monthly_expenses NUMERIC(12, 2), 
	savings_balance NUMERIC(15, 2), 
	checking_balance NUMERIC(15, 2), 
	investment_balance NUMERIC(15, 2), 
	investment_contribution NUMERIC(12, 2), 
	retirement_account_401k NUMERIC(15, 2), 
	retirement_account_401k_contribution NUMERIC(12, 2), 
	retirement_account_ira NUMERIC(15, 2), 
	retirement_account_ira_contribution NUMERIC(12, 2), 
	retirement_account_roth NUMERIC(15, 2), 
	retirement_account_roth_contribution NUMERIC(12, 2), 
	hsa_balance NUMERIC(15, 2), 
	hsa_contribution NUMERIC(12, 2), 
	spouse_hsa_balance NUMERIC(15, 2), 
	spouse_hsa_contribution NUMERIC(12, 2), 
	real_estate_value NUMERIC(15, 2), 
	other_assets_value NUMERIC(15, 2), 
	mortgage_balance NUMERIC(15, 2), 
	mortgage_payment NUMERIC(12, 2), 
	mortgage_rate NUMERIC(5, 2), 
	mortgage_years_left INTEGER, 
	credit_card_debt NUMERIC(15, 2), 
	student_loan_debt NUMERIC(15, 2), 
	other_debt NUMERIC(15, 2), 
	total_monthly_debt_payments NUMERIC(12, 2), 
	investment_experience VARCHAR, 
	risk_tolerance VARCHAR, 
	investment_timeline VARCHAR, 
	preferred_investment_types JSON, 
	market_volatility_comfort VARCHAR, 
	investment_rebalancing_preference VARCHAR, 
	id UUID NOT NULL, 
	password VARCHAR NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE ref_milestones (
	id UUID NOT NULL, 
	title VARCHAR NOT NULL, 
	description VARCHAR NOT NULL, 
	target_age INTEGER NOT NULL, 
	category VARCHAR NOT NULL, 
	icon VARCHAR NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	sort_order INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE ref_goals (
	id UUID NOT NULL, 
	title VARCHAR NOT NULL, 
	description VARCHAR, 
	category VARCHAR NOT NULL, 
	type goaltype NOT NULL, 
	icon VARCHAR NOT NULL, 
	default_target_offset INTEGER, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE multi_step_form_progress (
	current_step INTEGER NOT NULL, 
	completed_steps JSON, 
	form_data JSON, 
	is_completed BOOLEAN NOT NULL, 
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	last_updated TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE retirement_plans (
	user_id UUID NOT NULL, 
	plan_name VARCHAR NOT NULL, 
	plan_type VARCHAR NOT NULL, 
	start_age INTEGER NOT NULL, 
	retirement_age INTEGER NOT NULL, 
	end_age INTEGER NOT NULL, 
	spouse_start_age INTEGER, 
	spouse_retirement_age INTEGER, 
	spouse_end_age INTEGER, 
	social_security_start_age INTEGER, 
	spouse_social_security_start_age INTEGER, 
	estimated_social_security_benefit NUMERIC(10, 2) NOT NULL, 
	spouse_estimated_social_security_benefit NUMERIC(10, 2) NOT NULL, 
	portfolio_growth_rate NUMERIC(5, 2) NOT NULL, 
	inflation_rate NUMERIC(5, 2) NOT NULL, 
	pension_income NUMERIC(10, 2) NOT NULL, 
	spouse_pension_income NUMERIC(10, 2) NOT NULL, 
	other_retirement_income NUMERIC(10, 2) NOT NULL, 
	desired_annual_retirement_spending NUMERIC(10, 2) NOT NULL, 
	major_one_time_expenses NUMERIC(12, 2) NOT NULL, 
	major_expenses_description VARCHAR, 
	bond_growth_rate NUMERIC(5, 2) NOT NULL, 
	initial_net_worth NUMERIC(12, 2) NOT NULL, 
	total_lifetime_tax NUMERIC(12, 2) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE investment_accounts (
	user_id UUID NOT NULL, 
	account_name VARCHAR NOT NULL, 
	account_type VARCHAR NOT NULL, 
	balance NUMERIC(12, 2) NOT NULL, 
	contribution_amount NUMERIC(10, 2), 
	contribution_frequency VARCHAR, 
	annual_return NUMERIC(5, 2), 
	fees NUMERIC(5, 2), 
	is_retirement_account BOOLEAN NOT NULL, 
	account_owner VARCHAR NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE activities (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	activity_type VARCHAR NOT NULL, 
	title VARCHAR, 
	description VARCHAR NOT NULL, 
	date TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	metadata JSON, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE roth_conversion_plans (
	user_id UUID NOT NULL, 
	plan_name VARCHAR NOT NULL, 
	current_age INTEGER NOT NULL, 
	retirement_age INTEGER NOT NULL, 
	traditional_ira_balance NUMERIC(12, 2) NOT NULL, 
	current_tax_rate NUMERIC(5, 2) NOT NULL, 
	expected_retirement_tax_rate NUMERIC(5, 2) NOT NULL, 
	annual_income NUMERIC(10, 2) NOT NULL, 
	conversion_amount NUMERIC(12, 2) NOT NULL, 
	years_to_convert INTEGER NOT NULL, 
	expected_return NUMERIC(5, 2) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	notes VARCHAR, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE user_goals (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	ref_goal_id UUID, 
	custom_title VARCHAR, 
	custom_description VARCHAR, 
	custom_icon VARCHAR, 
	status VARCHAR NOT NULL, 
	target_date TIMESTAMP WITHOUT TIME ZONE, 
	progress INTEGER NOT NULL, 
	target_amount FLOAT, 
	current_amount FLOAT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(ref_goal_id) REFERENCES ref_goals (id)
);

CREATE TABLE annual_snapshots (
	plan_id UUID NOT NULL, 
	year INTEGER NOT NULL, 
	age INTEGER NOT NULL, 
	gross_income NUMERIC(12, 2) NOT NULL, 
	net_income NUMERIC(12, 2) NOT NULL, 
	total_expenses NUMERIC(12, 2) NOT NULL, 
	total_assets NUMERIC(12, 2) NOT NULL, 
	total_liabilities NUMERIC(12, 2) NOT NULL, 
	net_worth NUMERIC(12, 2) NOT NULL, 
	taxes_paid NUMERIC(12, 2) NOT NULL, 
	cumulative_tax NUMERIC(12, 2) NOT NULL, 
	income_breakdown JSON, 
	expense_breakdown JSON, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(plan_id) REFERENCES retirement_plans (id)
);

CREATE TABLE user_milestones (
	title VARCHAR NOT NULL, 
	description VARCHAR, 
	target_year INTEGER, 
	target_age INTEGER, 
	category VARCHAR, 
	icon VARCHAR, 
	id UUID NOT NULL, 
	plan_id UUID, 
	user_id UUID, 
	milestone_type VARCHAR NOT NULL, 
	is_completed BOOLEAN NOT NULL, 
	color VARCHAR NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(plan_id) REFERENCES retirement_plans (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE asset_allocations (
	id UUID NOT NULL, 
	account_id UUID NOT NULL, 
	asset_category VARCHAR NOT NULL, 
	percentage NUMERIC(5, 2) NOT NULL, 
	value NUMERIC(12, 2) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(account_id) REFERENCES investment_accounts (id)
);

CREATE TABLE security_holdings (
	id UUID NOT NULL, 
	account_id UUID NOT NULL, 
	ticker VARCHAR NOT NULL, 
	name VARCHAR, 
	percentage VARCHAR NOT NULL, 
	asset_class VARCHAR, 
	region VARCHAR, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(account_id) REFERENCES investment_accounts (id)
);

CREATE TABLE roth_conversion_scenarios (
	id UUID NOT NULL, 
	plan_id UUID NOT NULL, 
	year INTEGER NOT NULL, 
	age INTEGER NOT NULL, 
	conversion_amount NUMERIC(12, 2) NOT NULL, 
	tax_cost NUMERIC(12, 2) NOT NULL, 
	traditional_balance NUMERIC(12, 2) NOT NULL, 
	roth_balance NUMERIC(12, 2) NOT NULL, 
	total_tax_paid NUMERIC(12, 2) NOT NULL, 
	net_worth NUMERIC(12, 2) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(plan_id) REFERENCES roth_conversion_plans (id)
);

CREATE TABLE annual_snapshots_assets (
	id UUID NOT NULL, 
	snapshot_id UUID NOT NULL, 
	name VARCHAR NOT NULL, 
	type VARCHAR NOT NULL, 
	balance NUMERIC(12, 2) NOT NULL, 
	growth NUMERIC(10, 2) NOT NULL, 
	contribution NUMERIC(10, 2) NOT NULL, 
	withdrawal NUMERIC(10, 2) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(snapshot_id) REFERENCES annual_snapshots (id)
);

CREATE TABLE annual_snapshots_liabilities (
	id UUID NOT NULL, 
	snapshot_id UUID NOT NULL, 
	name VARCHAR NOT NULL, 
	type VARCHAR NOT NULL, 
	balance NUMERIC(12, 2) NOT NULL, 
	payment NUMERIC(10, 2) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(snapshot_id) REFERENCES annual_snapshots (id)
);

CREATE TABLE annual_snapshots_income (
	id UUID NOT NULL, 
	snapshot_id UUID NOT NULL, 
	source VARCHAR NOT NULL, 
	amount NUMERIC(12, 2) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(snapshot_id) REFERENCES annual_snapshots (id)
);

CREATE TABLE annual_snapshots_expenses (
	id UUID NOT NULL, 
	snapshot_id UUID NOT NULL, 
	category VARCHAR NOT NULL, 
	amount NUMERIC(12, 2) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(snapshot_id) REFERENCES annual_snapshots (id)
);

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO alembic_version (version_num) VALUES ('bfc36cb480ac') RETURNING alembic_version.version_num;



-- Grant usage on schema (usually public)
GRANT USAGE ON SCHEMA public TO reazy_dba;

-- Grant all privileges on all existing tables to reazy_dba
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO reazy_dba;

-- Ensure future tables created by other users are also accessible (optional but good idea)
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO reazy_dba;

-- Reference Data Seed File
-- Generated for Staging Environment Setup

-- RefGoals (6)
INSERT INTO ref_goals (id, title, description, category, type, icon, is_active, created_at) VALUES ('019b34be-2c7a-76d6-815a-ea0a8dcdd68d', 'Emergency Fund', 'Save 3-6 months of expenses', 'risk', 'EMERGENCY_FUND', 'ShieldCheck', True, NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO ref_goals (id, title, description, category, type, icon, is_active, created_at) VALUES ('019b34be-2c7b-791d-a0d9-8243b98d6400', 'Max 401(k)', 'Contribute the maximum annual amount to your 401(k)', 'retirement', 'RETIREMENT_401K', 'Briefcase', True, NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO ref_goals (id, title, description, category, type, icon, is_active, created_at) VALUES ('019b34be-2c7c-7470-b0cb-6d532eee4adc', 'Pay Off Debt', 'Eliminate high-interest consumer debt', 'financial', 'DEBT_PAYOFF', 'CreditCard', True, NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO ref_goals (id, title, description, category, type, icon, is_active, created_at) VALUES ('019b34be-2c7d-7757-aefc-b0acaddc877e', 'Pay Off Mortgage', 'Pay off your mortgage', 'lifestyle', 'MORTGAGE_PAYOFF', 'Home', True, NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO ref_goals (id, title, description, category, type, icon, is_active, created_at) VALUES ('019b34be-2c7e-7698-80d6-ca0a6d245a44', 'Health Savings', 'Fund your HSA for medical expenses', 'health', 'HEALTH_SAVINGS', 'HeartPulse', True, NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO ref_goals (id, title, description, category, type, icon, is_active, created_at) VALUES ('019b34be-2c7f-7710-9ef9-699eda2f84d2', 'Other Income', 'Establish additional income sources', 'investing', 'ADDITIONAL_INCOME', 'TrendingUp', True, NOW()) ON CONFLICT (id) DO NOTHING;

-- RefMilestones (6)
INSERT INTO ref_milestones (id, title, description, target_age, category, icon, is_active, sort_order, created_at, updated_at) VALUES ('019ae1e4-55e5-750d-9652-0fe935029854', 'Catch-up Contributions', 'Eligible for additional 401(k) and IRA contributions', 50, 'financial', 'dollar-sign', True, 1, NOW(), NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO ref_milestones (id, title, description, target_age, category, icon, is_active, sort_order, created_at, updated_at) VALUES ('019ae1e4-55e5-7cf7-ab28-39a9490b1329', 'Early Social Security', 'Eligible for reduced Social Security benefits (75% of full benefit)', 62, 'retirement', 'clock', True, 1, NOW(), NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO ref_milestones (id, title, description, target_age, category, icon, is_active, sort_order, created_at, updated_at) VALUES ('019ae1e4-55e5-7832-9d63-00ff492f6796', 'Medicare Eligibility', 'Eligible for Medicare health insurance', 65, 'healthcare', 'shield', True, 1, NOW(), NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO ref_milestones (id, title, description, target_age, category, icon, is_active, sort_order, created_at, updated_at) VALUES ('019ae1e4-55e5-716b-a877-1173f05ba877', 'Full Retirement Age', 'Eligible for full Social Security benefits', 67, 'retirement', 'clock', True, 1, NOW(), NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO ref_milestones (id, title, description, target_age, category, icon, is_active, sort_order, created_at, updated_at) VALUES ('019ae1e4-55e5-71a2-9692-5fa09641a77d', 'Required Minimum Distributions', 'Must begin taking RMDs from retirement accounts', 73, 'financial', 'dollar-sign', True, 1, NOW(), NOW()) ON CONFLICT (id) DO NOTHING;
INSERT INTO ref_milestones (id, title, description, target_age, category, icon, is_active, sort_order, created_at, updated_at) VALUES ('019ae1e4-55e5-7118-b8eb-b615dd8ea970', 'HSA Triple Tax Advantage', 'Health Savings Account contributions, growth, and withdrawals for medical expenses are all tax-free', 55, 'healthcare', 'shield', True, 2, NOW(), NOW()) ON CONFLICT (id) DO NOTHING;

COMMIT;