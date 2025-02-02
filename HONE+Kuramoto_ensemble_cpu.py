import numpy as np
import networkx as nx
from tqdm import tqdm
from scipy.linalg import eigh
from concurrent.futures import ThreadPoolExecutor

def HONE_worker_with_damped_kuramoto(adj_matrix, dim, iterations, tol, seed, dt, gamma, gamma_theta, K):
    """
    Harmonic Oscillator Network Embedding (HONE) with Damped Kuramoto Model.
    This function simulates a network of coupled harmonic oscillators where
    nodes experience both spatial interactions and phase synchronization effects
    governed by the Kuramoto model with damping.

    Parameters:
        adj_matrix (numpy.ndarray): Adjacency matrix representing the weighted network.
        dim (int): Dimensionality of the embedding space.
        iterations (int): Number of simulation steps.
        tol (float): Convergence threshold for stopping criteria.
        seed (int): Random seed for reproducibility.
        dt (float): Time step for numerical integration.
        gamma (float): Damping coefficient for spatial movement.
        gamma_theta (float): Damping coefficient for phase synchronization.
        K (float): Coupling strength in the Kuramoto model.

    Returns:
        tuple: (positions_history, phase_history, potential_energy_history, kinetic_energy_history, total_energy_history)
            - positions_history (list of numpy.ndarray): Time evolution of node positions.
            - phase_history (list of numpy.ndarray): Time evolution of node phases.
            - potential_energy_history (list of float): Evolution of the system’s potential energy.
            - kinetic_energy_history (list of float): Evolution of the system’s kinetic energy.
            - total_energy_history (list of float): Evolution of total system energy (kinetic + potential).
    """
    np.random.seed(seed)  # Set the random seed for reproducibility
    num_nodes = adj_matrix.shape[0]  # Number of nodes in the network

    # Initialize positions randomly in the embedding space
    positions = np.random.rand(num_nodes, dim)
    velocities = np.zeros_like(positions)  # Initial velocity set to zero

    # Initialize phases randomly between [0, 2π] and set initial phase velocities to zero
    phases = np.random.uniform(0, 2 * np.pi, num_nodes)
    phase_velocities = np.zeros(num_nodes)

    # Generate intrinsic frequencies from a normal distribution (mean = 0, variance = 1)
    intrinsic_frequencies = np.random.normal(0, 1, num_nodes)

    # Lists to store simulation history
    positions_history = [positions.copy()]
    phase_history = [phases.copy()]
    potential_energy_history = []
    kinetic_energy_history = []
    total_energy_history = []

    def calculate_forces(positions):
        """
        Compute forces acting on each node due to harmonic interactions with neighbors.
        Forces are computed using a distance-weighted interaction model based on adjacency matrix.
        """
        forces = np.zeros_like(positions)
        for i in range(num_nodes):
            # Compute displacement vectors between node i and all other nodes
            delta = positions - positions[i]
            distances = np.linalg.norm(delta, axis=1)  # Compute Euclidean distance
            mask = distances > 1e-6  # Avoid division by zero issues
            distances[~mask] = max(1e-6, np.min(distances[mask]))  # Regularize small distances
            # Compute force contributions from connected nodes
            forces[i] = np.sum(adj_matrix[i, mask][:, None] * (delta[mask] / distances[mask, None]), axis=0)
        return forces

    def compute_potential_energy(positions):
        """
        Compute potential energy of the system based on the harmonic interaction model.
        Each connected node pair contributes to the system’s energy based on their displacement.
        """
        return 0.5 * np.sum([
            adj_matrix[i, j] * max(np.linalg.norm(positions[i] - positions[j]), 1e-6)**2
            for i in range(num_nodes) for j in range(i)
        ])

    # Simulation loop
    for step in tqdm(range(iterations), desc="Simulating Damped Kuramoto-HONE", unit="iter"):
        # Compute forces and update positions using velocity Verlet-like scheme
        forces = calculate_forces(positions)
        accelerations = forces
        velocities += accelerations * dt - gamma * velocities  # Apply damping to velocity
        new_positions = positions + velocities * dt  # Update positions
        positions_history.append(new_positions.copy())

        # Compute phase dynamics using the Kuramoto model with damping
        phase_diffs = np.array([
            np.sum(adj_matrix[i] * np.sin(phases - phases[i])) for i in range(num_nodes)
        ])
        # Compute phase accelerations (including intrinsic frequency, coupling, and damping)
        phase_accelerations = intrinsic_frequencies + K * phase_diffs - gamma_theta * phase_velocities
        phase_velocities += phase_accelerations * dt  # Update phase velocities
        new_phases = phases + phase_velocities * dt  # Update phases
        phase_history.append(new_phases.copy())

        # Compute kinetic and potential energy of the system
        kinetic_energy = 0.5 * np.sum(np.linalg.norm(velocities, axis=1) ** 2)
        potential_energy = compute_potential_energy(new_positions)
        total_energy = kinetic_energy + potential_energy

        # Store energy history
        kinetic_energy_history.append(kinetic_energy)
        potential_energy_history.append(potential_energy)
        total_energy_history.append(total_energy)

        # Convergence check: if total movement is below threshold, stop simulation
        total_movement = np.sum(np.linalg.norm(new_positions - positions, axis=1))
        if total_movement < tol:
            print(f"Convergence achieved at iteration {step}")
            break

        # Update positions and phases for the next step
        positions = new_positions
        phases = new_phases

    return positions_history, phase_history, potential_energy_history, kinetic_energy_history, total_energy_history

def HONE_kuramoto_ensemble(G, dim=2, iterations=100, ensemble_size=100, tol=1e-4, dt=0.01, gamma=1.0, gamma_theta=0.1, K=0.5):
    """
    Perform Harmonic Oscillator Network Embedding (HONE) with Damped Kuramoto Model for an ensemble of simulations.
    This function runs multiple simulations with different random seeds and collects the full time evolution of positions,
    phases, and energy values.

    Parameters:
        G (networkx.Graph): Input graph to be embedded.
        dim (int): Number of dimensions for the embedding space.
        iterations (int): Maximum number of iterations for each simulation.
        ensemble_size (int): Number of ensemble realizations (seeds) to run.
        tol (float): Convergence tolerance for the total movement of positions.
        dt (float): Time step for numerical integration.
        gamma (float): Damping coefficient for spatial movement.
        gamma_theta (float): Damping coefficient for phase synchronization.
        K (float): Coupling strength in the Kuramoto model.

    Returns:
        tuple:
            - ensemble_positions (list of lists): List of position histories for each ensemble realization.
            - ensemble_phases (list of lists): List of phase histories for each ensemble realization.
            - ensemble_potential_energies (list of lists): List of potential energy histories.
            - ensemble_kinetic_energies (list of lists): List of kinetic energy histories.
            - ensemble_total_energies (list of lists): List of total energy histories.
    """
    # Convert the graph to an adjacency matrix (weighted or unweighted)
    if nx.is_weighted(G):
        adj_matrix = np.asarray(nx.to_numpy_array(G, weight="weight"))
    else:
        adj_matrix = np.asarray(nx.to_numpy_array(G))
        adj_matrix[adj_matrix > 0] = 1  # Convert to unweighted if needed

    results = [None] * ensemble_size

    # Use multi-threading for parallel execution of ensemble simulations
    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(
                HONE_worker_with_damped_kuramoto,
                adj_matrix, dim, iterations, tol, seed, dt, gamma, gamma_theta, K
            )
            for seed in range(ensemble_size)
        ]
        for i, future in enumerate(futures):
            results[i] = future.result()

    # Extract all histories from the results
    ensemble_positions = [result[0] for result in results]
    ensemble_phases = [result[1] for result in results]
    ensemble_potential_energies = [result[2] for result in results]
    ensemble_kinetic_energies = [result[3] for result in results]
    ensemble_total_energies = [result[4] for result in results]

    return ensemble_positions, ensemble_phases, ensemble_potential_energies, ensemble_kinetic_energies, ensemble_total_energies
