## Riegel Formula for Race Prediction

The Riegel formula predicts performance at a target race distance from a known race result:

T2 = T1 × (D2 / D1)^1.06

Where:
- T1 = known race time
- D1 = known race distance
- T2 = predicted time for target distance
- D2 = target distance
- 1.06 = fatigue exponent (Riegel's original value)

Example: 5K in 25:00 → predicted 10K?
T2 = 25:00 × (10000/5000)^1.06 = 25:00 × 2^1.06 = 25:00 × 2.085 = 52:07

## Adjusting the Exponent for Recreational Runners

Riegel's original 1.06 exponent was derived from world-record data. Recreational runners typically have a higher effective exponent (worse fatigue resistance) because:
- Less developed aerobic base relative to speed
- Less pacing discipline
- Lower training volume relative to race distance

Practical adjustments:
- Well-trained runners (60–80+ km/week): use 1.06
- Moderate training (40–60 km/week): use 1.08
- Lower training volume (<40 km/week): use 1.10

Using 1.08 for a recreational runner: 5K in 25:00 → 10K = 25:00 × 2^1.08 = 25:00 × 2.113 = 52:49

The difference grows at longer distances. For marathon prediction from a half marathon result:
- Professional exponent (1.06): HM 1:45:00 → marathon 3:37:58
- Recreational exponent (1.10): HM 1:45:00 → marathon 3:42:44
- Untrained (1.15): HM 1:45:00 → marathon 3:50:58

## VDOT-Based Race Prediction

VDOT provides a more holistic prediction method that accounts for the VO2max-efficiency relationship.

Steps:
1. Calculate VDOT from known race: use vdot_from_race(distance_m, time_min) formula
2. Look up predicted times for target distances at that VDOT in the vdot_paces.json table

VDOT predictions are generally more accurate than Riegel for distances with very different energy system demands (e.g., 1500m vs marathon).

## Common Prediction Errors

The marathon is consistently over-predicted (athletes run slower than predicted) due to:
- Glycogen depletion at 30–35 km alters running economy dramatically
- Heat, wind, and race-day conditions compound late-race fatigue
- Pacing errors — going out too fast amplifies the cost

A practical correction: multiply any predicted marathon time by 1.02–1.05 for recreational runners to account for the wall effect. Especially if the athlete's longest training run has been under 30 km.

The 5K is sometimes under-predicted for runners with high anaerobic capacity (fast but lower aerobic base). VDOT handles this better than Riegel.

## Race Prediction from Training Metrics

Without a recent race result, VDOT can be estimated from:
- Threshold pace (T-pace): If you know your current threshold pace, find the matching VDOT in the table and use that for predictions
- Aerobic efficiency trend: improving AE suggests improving VDOT even without a time trial

The most reliable estimate: a recent 5K time trial (full effort) gives clean VDOT that predicts well across all distances.

## Interpreting Predictions for Coaching

When an athlete's target marathon time implies a VDOT significantly above what their 5K or 10K performance suggests, the discrepancy predicts a hard day. For example:
- Athlete runs 5K in 25:00 (VDOT ≈ 41, marathon prediction ≈ 4:00–4:05 with recreational correction)
- Athlete wants to run 3:30 marathon
- This is a 12% gap — very risky without major fitness improvement

Coaching response to unrealistic goals: present the data factually (their current VDOT and its marathon prediction), explain what training changes would be required, and help set an intermediate goal race to recalibrate expectations.
