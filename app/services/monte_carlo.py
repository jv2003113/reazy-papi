import numpy as np
from typing import List, Dict
from pydantic import BaseModel

class SimulationResult(BaseModel):
    percentiles: Dict[str, List[float]]  # "10th", "50th", "90th" -> list of balances by year
    success_rate: float
    median_ending_balance: float
    years: List[int]

class MonteCarloService:
    @staticmethod
    def run_simulation(
        current_balance: float,
        annual_contribution: float,
        years_to_retirement: int,
        total_years: int,
        annual_withdrawal: float,
        risk_profile: str = "moderate",
        num_simulations: int = 1000
    ) -> SimulationResult:
        """
        Runs a Monte Carlo simulation to project future portfolio outcomes.
        
        This method performs `num_simulations` iterations of possible market returns based on the 
        selected `risk_profile`. It accounts for annual contributions (accumulation phase) 
        and withdrawals (retirement phase).

        Args:
            risk_profile (str): Determines the mean (mu) and volatility (sigma) of returns.
                - Conservative: Lower growth, lower volatility.
                - Aggressive: Higher potential growth, higher volatility.
                
        Returns:
            SimulationResult: success rates, median balances, and 10th/90th percentile outcomes.
        """
        # Determine strict market parameters based on risk profile
        profiles = {
            "conservative": (0.05, 0.06),
            "moderate": (0.07, 0.12),
            "aggressive": (0.09, 0.18)
        }
        
        mu, sigma = profiles.get(risk_profile.lower(), profiles["moderate"])
        
        # Initialize simulation array
        sim_balances = np.zeros((num_simulations, total_years + 1))
        sim_balances[:, 0] = current_balance
        
        for t in range(1, total_years + 1):
            # Generate random returns
            returns = np.random.normal(mu, sigma, num_simulations)
            
            # Phase logic
            if t <= years_to_retirement:
                 # Accumulation: Add contribution
                 sim_balances[:, t] = sim_balances[:, t-1] * (1 + returns) + annual_contribution
            else:
                 # Decumulation: Subtract withdrawal (Assume withdrawal happens at start of year for safety?)
                 # Standard is usually end of year or mid-year.
                 # Let's do: Grow then withdraw.
                 sim_balances[:, t] = sim_balances[:, t-1] * (1 + returns) - annual_withdrawal
                 
            # Clamp to 0 (Bankruptcy)
            sim_balances[:, t] = np.maximum(sim_balances[:, t], 0)
            
        # Analyze results
        percentiles = {}
        for p in [10, 50, 90]:
            ts = np.percentile(sim_balances, p, axis=0)
            percentiles[f"{p}th"] = ts.tolist()
            
        # Success Rate: % of runs that did NOT hit 0 at the end (or anywhere? usually "at end of plan")
        # Assuming we clamp to 0, check if balance > 0
        success_count = np.sum(sim_balances[:, -1] > 0)
        success_rate = (success_count / num_simulations) * 100.0
        
        median_ending = np.median(sim_balances[:, -1])
        
        return SimulationResult(
            percentiles=percentiles,
            success_rate=round(success_rate, 1),
            median_ending_balance=median_ending,
            years=list(range(total_years + 1))
        )
