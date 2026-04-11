TOKENSTORE_DIR = ".garmin_tokens"
DB_PATH = "garmin_data.db"
FETCH_BATCH_SIZE = 20
DETAIL_FETCH_DELAY_SEC = 0.5

# REI component weights (must sum to 1.0 when all sensors present)
REI_WEIGHT_CADENCE = 0.30
REI_WEIGHT_OSCILLATION = 0.25
REI_WEIGHT_AEROBIC_EFF = 0.30
REI_WEIGHT_GROUND_CONTACT = 0.15

# Physiological targets for normalization
CADENCE_TARGET_SPM = 170        # full cadence (both feet); excellent ~180
OSCILLATION_TARGET_CM = 8.0     # cm; excellent ~6.5
GROUND_CONTACT_TARGET_MS = 240  # ms; excellent ~200

# AE baseline uses best N% of qualifying runs
AE_BASELINE_PERCENTILE = 20     # top 20% by aerobic efficiency
AE_BASELINE_MIN_DURATION_SEC = 1200  # 20 min minimum to count toward baseline

# Recalibrate AE baseline after this many new runs are added
AE_RECALIBRATE_AFTER_NEW_RUNS = 10

# VDOT estimation
VDOT_EFFORT_CORRECTION = 1.10
VDOT_HR_LOWER_FRACTION = 0.70
VDOT_HR_UPPER_FRACTION = 0.92
VDOT_ESTIMATE_PERCENTILE = 90
VDOT_MIN_RUN_DURATION_SEC = 1200

# RAG knowledge base
KNOWLEDGE_DIR = "knowledge"
KNOWLEDGE_DB_PATH = "chroma_db"
KNOWLEDGE_RETRIEVAL_K = 4
KNOWLEDGE_SIMILARITY_THRESHOLD = 0.4
