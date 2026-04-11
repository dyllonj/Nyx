## Heat Acclimatization

Heat acclimatization is a physiological adaptation to running in hot conditions that significantly reduces cardiovascular strain and improves performance in the heat. Adaptations include: increased plasma volume (5-15%), earlier and greater sweat response, lower HR at the same pace, lower core temperature at the same pace, and reduced RPE.

Timeline: meaningful adaptations occur in 5-7 days of heat exposure. Full acclimatization takes 10-14 days. Exposures should be 60-90 minutes in heat.

How to accelerate acclimatization:
- Run in the hottest part of the day for 10-14 consecutive days leading up to a hot race
- Heat loading techniques: sauna post-run (20-30 min at 80-90°C) for 7-10 sessions can partially substitute for outdoor heat training
- Exercising in heat stress (even overdressing in mild weather) produces partial adaptation

Acclimatization carries over: if you train in cool conditions and race in heat, 5-7 days of pre-race acclimatization (arrive early, run easy in heat) significantly reduces the performance penalty.

Deacclimatization: heat adaptations fade within 2-4 weeks of returning to cool conditions.

## WBGT vs Dry Bulb Temperature

Dry bulb temperature (what standard weather apps show) underestimates heat stress because it ignores humidity and solar radiation. Wet Bulb Globe Temperature (WBGT) incorporates these factors and is the standard used in military and sports medicine for heat safety decisions.

**WBGT vs dry bulb:** at high humidity (>80%), WBGT can be 5-10°C higher than dry bulb. A "comfortable" 22°C morning with 85% humidity may have a WBGT of 20-22°C, representing genuinely dangerous race conditions.

**Race risk categories (ACSM guidelines for road races):**
- WBGT < 10°C: low risk (flag: white)
- WBGT 10-17°C: low-moderate risk (flag: green) — good conditions
- WBGT 17-23°C: moderate risk (flag: yellow) — caution, adjust pace
- WBGT 23-28°C: high risk (flag: red) — consider postponing; high risk for novice runners
- WBGT > 28°C: extreme risk (flag: black) — cancel race or defer to experienced athletes only

Approximate WBGT from dry bulb: WBGT ≈ 0.7 × wet bulb temperature + 0.1 × dry bulb temperature + 0.2 × globe temperature. Without specialized equipment, use the Steadman apparent temperature ("feels like") as a rough proxy.

## Existing Pace Adjustment Accuracy

The weather_adjustments.json file uses 5%/8%/12% pace adjustments for mild/moderate/hot conditions. These are reasonable approximations but deserve nuance:

**Research findings:**
- Ely et al. (2007) studied marathon performance across temperature ranges: performance declined linearly with temperature. For a 4-hour marathoner: ~1.5-2 min/°C above 10°C wet bulb. For a 3-hour marathoner: ~45 sec/°C.
- The adjustments are NOT linear with temperature — they accelerate. Going from 15°C to 25°C is worse than going from 5°C to 15°C for the same 10-degree increase.
- **Recreational runners (>4 hours) are more sensitive to heat than elites.** The 5%/8%/12% figures may underestimate impact for slower runners. A 5-hour marathoner may lose 15-20% in extreme heat.
- Humidity matters as much as temperature. Dry heat at 32°C is less stressful than 28°C with 90% humidity.

**Better adjusted guidelines:**
- Mild heat (25-28°C dry bulb, moderate humidity): 5-8% pace adjustment
- Moderate heat (28-32°C, or <32°C with high humidity): 8-15% adjustment
- Hot (>32°C or high humidity): 12-20%+ adjustment; seriously consider whether racing is appropriate

## Cold Weather Running

Cold running is generally less detrimental to performance than heat. Most trained runners perform comparably in 5-10°C vs ideal conditions (10-15°C). Below 0°C, some performance decrement occurs from bronchospasm, increased respiratory heat loss, and muscle stiffness.

**Performance impact:**
- 5-10°C: neutral to slightly beneficial vs 15-20°C for trained runners
- 0-5°C: minimal impact with proper warm-up
- Below -10°C: bronchospasm risk increases; performance may decline 2-5%
- Below -20°C: frostbite risk on exposed skin; limit outdoor running

**Cold-weather gear priorities:** hands and head lose the most heat; warm extremities while allowing some torso ventilation to prevent overheating once warmed up.

**Safety threshold:** wind chill below -27°C (-17°F) is the general threshold below which frostbite on exposed skin can occur in under 30 minutes. Running becomes inadvisable without full face coverage.

Warm-up: cold weather requires a longer warm-up (10-15 min easy before any intensity) — muscle tissue is stiffer and injury risk is elevated if running hard in the cold without adequate warm-up.

## Air Quality and AQI Thresholds

Air quality index (AQI) affects respiratory stress during running. At high intensity, breathing rate increases 5-10×, dramatically increasing pollutant exposure.

**AQI thresholds for running:**
- AQI 0-50 (Good): no restrictions, run normally
- AQI 51-100 (Moderate): generally safe; sensitive individuals (asthma, cardiovascular conditions) should reduce intensity
- AQI 101-150 (Unhealthy for Sensitive Groups): reduce intensity; limit duration for all runners
- AQI 151-200 (Unhealthy): run indoors or postpone; outdoor intensity work not recommended
- AQI 201-300 (Very Unhealthy): do not run outdoors
- AQI >300 (Hazardous): avoid all outdoor exertion

Particle size: PM2.5 (fine particles) penetrates deepest into lungs and is most harmful. PM2.5 AQI is the most relevant metric for runners. Check real-time AQI at weather apps or AirNow (US).

Wildfire smoke is particularly high in PM2.5. During active smoke events, even "moderate" visual haze may represent PM2.5 concentrations that warrant moving indoors.

## Altitude Effects on Running Performance

At altitude, reduced oxygen partial pressure forces the cardiovascular system to work harder to deliver the same oxygen to muscles. Performance declines predictably with elevation above ~1000m.

**Performance decline per 1000m elevation:**
- Sea level to 1000m: ~1.5-2% slower for distances 5K and longer
- 1000m to 2000m: additional 2-3% per 1000m
- 2500m (common US mountain race elevation): expect 4-8% performance decline on arrival

**Acclimatization timeline:**
- Days 1-3: worst performance (acute mountain sickness possible above 2500m)
- Days 4-7: partial adaptation, performance improves
- 2-3 weeks: near-full acclimatization for moderate altitudes (1500-2500m)
- Full acclimatization at high altitude (>3000m): 4-6 weeks

Practical options: arrive >10 days early for full adaptation, OR arrive <24 hours before race to compete before full acute effects set in (used by some elite athletes), OR train at altitude for 3-4 weeks then descend 2-3 weeks before race ("live high train low").

Garmin metrics at altitude: HR at the same pace will be elevated 5-15+ bpm until acclimatized. AE (aerobic efficiency) will appear to worsen on arrival and recover over 1-2 weeks. REI may drop due to HR component. This is physiological, not a fitness decline.

## Wind Correction for Race Pace

Wind significantly affects running economy. Headwind is more costly than the tailwind benefit it would offset (due to aerodynamic drag increasing quadratically with speed).

**Approximate corrections:**
- 10 km/h headwind: add ~5-8 sec/km for a 4-min/km runner, ~8-12 sec/km for a 5-min/km runner
- 20 km/h headwind: add ~15-20 sec/km (a significant impact — equivalent to 2-3% pace loss)
- Tailwind: benefits are roughly 50-60% of the headwind penalty (diminishing returns due to reduced propulsive benefit)

**Coaching implication:** on windy race days, adjust pace targets accordingly. Athletes who chase their PR pace into a headwind in the first half typically blow up. In a point-to-point race with a headwind on the return, bank easy effort (not time) in the first half.
