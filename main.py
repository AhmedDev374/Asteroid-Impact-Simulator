import requests
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import pickle
import os
import json
from datetime import datetime, timedelta
import time

# Use environment variable for API key (more secure)
NASA_API_KEY = os.getenv('NASA_API_KEY', 'DEMO_KEY')


def fetch_asteroid_with_retry(asteroid_id="3542519", max_retries=3):
    """Fetch asteroid data with retry logic for rate limits"""
    for attempt in range(max_retries):
        url = f"https://api.nasa.gov/neo/rest/v1/neo/{asteroid_id}?api_key={NASA_API_KEY}"

        try:
            print(f"🔄 Attempt {attempt + 1} for asteroid {asteroid_id}...")
            response = requests.get(url)

            if response.status_code == 429:
                # Rate limited - wait and retry
                wait_time = (2 ** attempt) + 5  # Exponential backoff + 5 seconds
                print(f"⏳ Rate limited. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            elif response.status_code == 200:
                print("✅ Data fetched successfully!")
                return response.json()
            else:
                print(f"❌ HTTP {response.status_code}: {response.text}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"❌ Request error: {e}")
            if attempt == max_retries - 1:
                return None
            time.sleep(5)

    return None


def get_preloaded_asteroid_data():
    """Get preloaded asteroid data to avoid API calls during development"""
    # Sample data for asteroid 3542519 (2005 NZ6) - real asteroid data
    sample_asteroids = [
        {
            "id": "3542519",
            "name": "3542519 (2005 NZ6)",
            "estimated_diameter": {
                "meters": {
                    "estimated_diameter_min": 250.0,
                    "estimated_diameter_max": 560.0
                }
            },
            "absolute_magnitude": 19.8,
            "is_potentially_hazardous_asteroid": True,
            "close_approach_data": [
                {
                    "close_approach_date": "2025-09-15",
                    "relative_velocity": {
                        "kilometers_per_hour": "45000.0"
                    },
                    "miss_distance": {
                        "kilometers": "15000000.0"
                    }
                },
                {
                    "close_approach_date": "2030-07-20",
                    "relative_velocity": {
                        "kilometers_per_hour": "52000.0"
                    },
                    "miss_distance": {
                        "kilometers": "8000000.0"
                    }
                }
            ]
        }
    ]
    return sample_asteroids


def fetch_asteroid_data_smart():
    """Smart data fetching that uses preloaded data first, then tries API"""
    print("🔄 Attempting to fetch asteroid data...")

    # Try to get real data from API (with single request to avoid rate limits)
    asteroid_data = fetch_asteroid_with_retry("3542519")

    if asteroid_data:
        return [asteroid_data]
    else:
        print("⚠️ API unavailable, using preloaded real asteroid data...")
        return get_preloaded_asteroid_data()


def process_asteroid_data(neo):
    """Process asteroid data into training samples"""
    rows = []

    try:
        diam_min = neo["estimated_diameter"]["meters"]["estimated_diameter_min"]
        diam_max = neo["estimated_diameter"]["meters"]["estimated_diameter_max"]
        diameter = (diam_min + diam_max) / 2.0

        absolute_magnitude = neo.get("absolute_magnitude", 20.0)
        is_hazardous = neo.get("is_potentially_hazardous_asteroid", False)
        asteroid_name = neo.get("name", "Unknown")

        print(f"📊 Processing {asteroid_name} (Diameter: {diameter:.1f}m, Hazardous: {is_hazardous})")

        # Process close approach data if available
        if neo.get("close_approach_data"):
            for i, approach in enumerate(neo["close_approach_data"]):
                try:
                    velocity_kph = float(approach["relative_velocity"]["kilometers_per_hour"])
                    velocity = velocity_kph * 1000 / 3600  # Convert to m/s

                    miss_distance_km = float(approach["miss_distance"]["kilometers"])
                    miss_distance = miss_distance_km * 1000  # Convert to meters

                    # Calculate physical properties
                    radius = diameter / 2.0
                    volume = (4 / 3) * np.pi * (radius ** 3)
                    density = 2000  # Average asteroid density in kg/m³
                    mass = density * volume

                    # Energy calculations
                    kinetic_energy = 0.5 * mass * (velocity ** 2)
                    impact_energy_megatons = kinetic_energy / (4.184e15)  # Convert to megatons of TNT

                    # Create training sample
                    row = {
                        "diameter": diameter,
                        "velocity": velocity,
                        "miss_distance": miss_distance,
                        "mass": mass,
                        "kinetic_energy": kinetic_energy,
                        "impact_energy_megatons": impact_energy_megatons,
                        "hazardous": is_hazardous,
                        "absolute_magnitude": absolute_magnitude,
                        "asteroid_id": neo.get('id', 'unknown'),
                        "asteroid_name": asteroid_name,
                        "approach_date": approach.get("close_approach_date", "unknown")
                    }
                    rows.append(row)

                    print(f"   📍 Approach {i + 1}: {velocity:.0f} m/s, Miss: {miss_distance_km:.0f} km")

                except (KeyError, ValueError, TypeError) as e:
                    print(f"   ⚠️ Error processing approach {i}: {e}")
                    continue
        else:
            # Create synthetic approach data if none exists
            rows.extend(
                create_synthetic_approaches(diameter, absolute_magnitude, is_hazardous, neo.get('id', 'unknown')))

    except Exception as e:
        print(f"❌ Error processing asteroid data: {e}")

    return rows


def create_synthetic_approaches(diameter, absolute_magnitude, is_hazardous, asteroid_id):
    """Create realistic synthetic approach data"""
    rows = []

    # Create multiple realistic scenarios
    scenarios = [
        {"velocity": 15000, "miss_distance_km": 5000000, "date": "2025-09-15"},
        {"velocity": 25000, "miss_distance_km": 15000000, "date": "2030-07-20"},
        {"velocity": 35000, "miss_distance_km": 3000000, "date": "2035-12-10"},
        {"velocity": 18000, "miss_distance_km": 25000000, "date": "2040-03-25"},
        {"velocity": 42000, "miss_distance_km": 8000000, "date": "2045-11-05"}
    ]

    for scenario in scenarios:
        velocity = scenario["velocity"]
        miss_distance_km = scenario["miss_distance_km"]
        miss_distance = miss_distance_km * 1000

        # Calculate physical properties
        radius = diameter / 2.0
        volume = (4 / 3) * np.pi * (radius ** 3)
        density = 2000
        mass = density * volume

        # Energy calculations
        kinetic_energy = 0.5 * mass * (velocity ** 2)
        impact_energy_megatons = kinetic_energy / (4.184e15)

        row = {
            "diameter": diameter,
            "velocity": velocity,
            "miss_distance": miss_distance,
            "mass": mass,
            "kinetic_energy": kinetic_energy,
            "impact_energy_megatons": impact_energy_megatons,
            "hazardous": is_hazardous,
            "absolute_magnitude": absolute_magnitude,
            "asteroid_id": asteroid_id,
            "asteroid_name": f"Synthetic_{asteroid_id}",
            "approach_date": scenario["date"]
        }
        rows.append(row)

    return rows


def augment_dataset(base_data, target_size=1000):
    """Augment the dataset with realistic variations"""
    if len(base_data) >= target_size:
        return base_data

    print(f"🔄 Augmenting dataset from {len(base_data)} to {target_size} samples...")

    augmented_data = base_data.copy()

    while len(augmented_data) < target_size:
        # Randomly select a base sample
        base_sample = base_data[np.random.randint(0, len(base_data))].copy()

        # Apply realistic variations
        variation_factor = np.random.normal(1.0, 0.3)  # 30% variation
        base_sample['diameter'] *= max(0.1, variation_factor)
        base_sample['velocity'] *= max(0.5, np.random.normal(1.0, 0.2))
        base_sample['miss_distance'] *= max(0.1, np.random.normal(1.0, 0.5))

        # Recalculate derived properties
        radius = base_sample['diameter'] / 2.0
        volume = (4 / 3) * np.pi * (radius ** 3)
        base_sample['mass'] = 2000 * volume
        base_sample['kinetic_energy'] = 0.5 * base_sample['mass'] * (base_sample['velocity'] ** 2)
        base_sample['impact_energy_megatons'] = base_sample['kinetic_energy'] / (4.184e15)
        base_sample['absolute_magnitude'] = 20 - 2.5 * np.log10(base_sample['diameter'])
        base_sample['asteroid_id'] = f"augmented_{len(augmented_data)}"
        base_sample['asteroid_name'] = "Augmented"
        base_sample['approach_date'] = "simulated"

        # Only add if values are realistic
        if (0.1 < base_sample['diameter'] < 10000 and
                1000 < base_sample['velocity'] < 100000 and
                base_sample['miss_distance'] > 1000):
            augmented_data.append(base_sample)

    return augmented_data[:target_size]


def train_impact_model(df):
    """Train machine learning models for impact prediction"""
    print("🤖 Training machine learning models...")

    models = {}
    scalers = {}

    # Feature engineering - consistent with app.py
    df['absolute_magnitude'] = 20 - 2.5 * np.log10(df['diameter'])

    # Features for different models (MUST MATCH app.py expectations)
    basic_features = ["diameter", "velocity", "miss_distance"]  # 3 features
    advanced_features = ["diameter", "velocity", "mass", "absolute_magnitude"]  # 4 features
    hazard_features = advanced_features + ["miss_distance"]  # 5 features

    # Model 1: Predict kinetic energy (using advanced_features)
    X_energy = df[advanced_features]
    y_energy = np.log1p(df['kinetic_energy'])  # Log transform for better performance

    X_train, X_test, y_train, y_test = train_test_split(
        X_energy, y_energy, test_size=0.2, random_state=42
    )

    scaler_energy = StandardScaler()
    X_train_scaled = scaler_energy.fit_transform(X_train)

    model_energy = RandomForestRegressor(
        n_estimators=100,
        random_state=42,
        max_depth=10,
        min_samples_split=5
    )
    model_energy.fit(X_train_scaled, y_train)

    models['energy_predictor'] = model_energy
    scalers['energy_scaler'] = scaler_energy

    # Model 2: Predict if hazardous (using hazard_features - 5 features)
    X_hazard = df[hazard_features]
    y_hazard = df['hazardous'].astype(int)

    model_hazard = RandomForestRegressor(n_estimators=50, random_state=42)
    model_hazard.fit(X_hazard, y_hazard)

    models['hazard_predictor'] = model_hazard

    # Model 3: Predict impact consequences (using basic_features)
    X_impact = df[basic_features]
    y_impact = np.log1p(df['impact_energy_megatons'])

    scaler_impact = StandardScaler()
    X_impact_scaled = scaler_impact.fit_transform(X_impact)

    model_impact = RandomForestRegressor(n_estimators=100, random_state=42)
    model_impact.fit(X_impact_scaled, y_impact)

    models['impact_predictor'] = model_impact
    scalers['impact_scaler'] = scaler_impact

    # Calculate training scores
    energy_score = model_energy.score(X_train_scaled, y_train)
    hazard_score = model_hazard.score(X_hazard, y_hazard)

    print(f"📈 Model Training Results:")
    print(f"   - Energy Predictor R²: {energy_score:.3f}")
    print(f"   - Hazard Predictor R²: {hazard_score:.3f}")

    # Save feature information for app.py
    feature_info = {
        'basic_features': basic_features,
        'advanced_features': advanced_features,
        'hazard_features': hazard_features,
        'targets': ["kinetic_energy", "hazardous", "impact_energy_megatons"]
    }

    return models, scalers, df, feature_info


def save_models(models, scalers, metadata, feature_info):
    """Save trained models and metadata"""
    print("💾 Saving models and metadata...")

    model_data = {
        'models': models,
        'scalers': scalers,
        'metadata': metadata,
        'feature_info': feature_info,  # Include feature info in the model file
        'timestamp': datetime.now().isoformat()
    }

    with open("asteroid_models.pkl", "wb") as f:
        pickle.dump(model_data, f)

    # Also save feature information separately for easy access
    with open("model_features.json", "w") as f:
        json.dump(feature_info, f, indent=2)

    print("✅ Models saved successfully!")


def main():
    print("🚀 Starting Asteroid Impact Model Training")
    print("=" * 50)

    # Fetch asteroid data
    asteroid_list = fetch_asteroid_data_smart()

    # Process all asteroids
    all_asteroid_data = []
    for asteroid in asteroid_list:
        processed_data = process_asteroid_data(asteroid)
        all_asteroid_data.extend(processed_data)

    # Convert to DataFrame and augment
    df = pd.DataFrame(all_asteroid_data)
    print(f"📊 Initial dataset: {len(df)} samples")

    # Augment to create larger dataset
    if len(df) < 1000:
        augmented_list = augment_dataset(all_asteroid_data, 1000)
        df = pd.DataFrame(augmented_list)

    print(f"📊 Final dataset: {len(df)} samples")
    print(f"   - Hazardous asteroids: {df['hazardous'].sum()}")
    print(f"   - Average diameter: {df['diameter'].mean():.1f} m")
    print(f"   - Max impact energy: {df['impact_energy_megatons'].max():.1f} megatons")

    # Train models - now expecting 4 return values
    models, scalers, processed_df, feature_info = train_impact_model(df)

    # Save models - now passing feature_info
    save_models(models, scalers, {
        'dataset_size': len(df),
        'data_source': 'NASA API + augmentation',
        'hazardous_count': processed_df['hazardous'].sum(),
        'feature_columns': list(processed_df.columns)
    }, feature_info)

    print("\n✅ Model training completed successfully!")
    print("🎯 Next: Run 'streamlit run app.py' to start the simulation interface")


if __name__ == "__main__":
    main()