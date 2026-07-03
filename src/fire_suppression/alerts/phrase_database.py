"""Fire alert and evacuation phrase database with English and Swahili translations.

# AUD-004 — Phrase Database (200 phrases)

Pre-loaded with 200 phrases for instant TTS playback:
- 100 common fire alert/status phrases
- 100 evacuation guidance phrases with room names and directions

All phrases use the 🚨 Aconitum Napellus (Panic Responder) personality
for emergency alerts and 🔥 Phosphorus (Charismatic Communicator)
for evacuation guidance — the optimal remedy pairing for fire safety.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


# ── CATEGORY 1: Fire Alert Phrases (100 phrases) ──
# Uses 🚨 Aconitum Napellus personality — urgent, direct, authoritative

FIRE_ALERT_PHRASES: list[dict] = [
    # Core fire detection alerts (1-20)
    {"id": "fire_detected", "en": "Fire detected. Evacuate immediately.", "sw": "Moto umeonekana. Ondoka mara moja.", "cat": "alert", "pri": 3},
    {"id": "fire_detected_zone", "en": "Fire detected in {zone}. Evacuate immediately.", "sw": "Moto umeonekana {zone}. Ondoka mara moja.", "cat": "alert", "pri": 3},
    {"id": "smoke_detected", "en": "Smoke detected. Leave the building now.", "sw": "Moshi umeonekana. Ondoka jengoni sasa.", "cat": "alert", "pri": 3},
    {"id": "smoke_detected_zone", "en": "Smoke detected in {zone}. Leave now.", "sw": "Moshi umeonekana {zone}. Ondoka sasa.", "cat": "alert", "pri": 3},
    {"id": "heat_surge", "en": "Temperature surge detected. Fire confirmed.", "sw": "Ongezeko la joto limeonekana. Moto umehakikishwa.", "cat": "alert", "pri": 3},
    {"id": "flame_detected", "en": "Open flame detected. Evacuate immediately.", "sw": "Moto wazi umeonekana. Ondoka mara moja.", "cat": "alert", "pri": 3},
    {"id": "co_detected", "en": "Carbon monoxide detected. Leave the area now.", "sw": "Monoksidi kaboni imeonekana. Ondoka eneo hili sasa.", "cat": "alert", "pri": 3},
    {"id": "multi_sensor_alert", "en": "Multiple sensors confirm fire. Evacuate now.", "sw": "Vihisio kadhaa vimehakikisha moto. Ondoka sasa.", "cat": "alert", "pri": 3},
    {"id": "fire_spreading", "en": "Fire is spreading. Evacuate immediately.", "sw": "Moto unaenea. Ondoka mara moja.", "cat": "alert", "pri": 3},
    {"id": "fire_confirmed", "en": "Fire confirmed by multiple systems. Leave now.", "sw": "Moto umehakikishwa na mifumo mingi. Ondoka sasa.", "cat": "alert", "pri": 3},
    {"id": "suppression_activated", "en": "Fire suppression system activated.", "sw": "Mfumo wa kuzima moto umeamilishwa.", "cat": "alert", "pri": 2},
    {"id": "suppression_failed", "en": "Fire suppression failed. Evacuate immediately.", "sw": "Kuzima moto kumeshindwa. Ondoka mara moja.", "cat": "alert", "pri": 3},
    {"id": "sprinkler_activated", "en": "Sprinkler system activated.", "sw": "Mfumo wa sprinkler umeamilishwa.", "cat": "alert", "pri": 2},
    {"id": "extinguisher_deployed", "en": "Fire extinguisher deployed.", "sw": "Kizima moto kimetumwa.", "cat": "alert", "pri": 2},
    {"id": "gas_shutoff", "en": "Gas supply shut off. Fire contained.", "sw": "Mfumo wa gesi umezimwa. Moto umezingirwa.", "cat": "alert", "pri": 2},
    {"id": "power_isolated", "en": "Electrical power isolated. Safe to approach.", "sw": "Umeme umetengwa. Salama kukaribia.", "cat": "alert", "pri": 2},
    {"id": "elevator_recalled", "en": "Elevators recalled to ground floor. Do not use.", "sw": "Lifti zimerudishwa chini. Usitumie.", "cat": "alert", "pri": 2},
    {"id": "hvac_shutdown", "en": "Ventilation system shut down. Smoke contained.", "sw": "Mfumo wa hewa umezimwa. Moshi umezingirwa.", "cat": "alert", "pri": 2},
    {"id": "zone_isolated", "en": "Fire zone isolated. Safe to evacuate adjacent areas.", "sw": "Eneo la moto limezingirwa. Salama kuondoka maeneo ya jirani.", "cat": "alert", "pri": 2},
    {"id": "all_clear_pending", "en": "Fire under control. Awaiting all-clear confirmation.", "sw": "Moto umezingirwa. Subiri uthibitisho wa usalama.", "cat": "alert", "pri": 1},

    # Zone-specific alerts (21-40)
    {"id": "kitchen_fire", "en": "Kitchen fire detected. Do not use water on grease fire.", "sw": "Moto jikoni umeonekana. Usitumie maji kwenye moto wa mafuta.", "cat": "alert", "pri": 3},
    {"id": "bedroom_fire", "en": "Fire detected in bedroom. Check for occupants.", "sw": "Moto umeonekana chumbani. Angalia watu waliomo.", "cat": "alert", "pri": 3},
    {"id": "living_room_fire", "en": "Fire detected in living room. Evacuate immediately.", "sw": "Moto umeonekana chumba cha mapokezi. Ondoka mara moja.", "cat": "alert", "pri": 3},
    {"id": "basement_fire", "en": "Basement fire detected. Use stairwell B.", "sw": "Moto chini ya jengo umeonekana. Tumia ngazi B.", "cat": "alert", "pri": 3},
    {"id": "garage_fire", "en": "Garage fire detected. Avoid overhead doors.", "sw": "Moto gerejani umeonekana. Epuka milango ya juu.", "cat": "alert", "pri": 3},
    {"id": "office_fire", "en": "Office fire detected. Proceed to nearest exit.", "sw": "Moto ofisini umeonekana. Enda kwa mlango wa karibu.", "cat": "alert", "pri": 3},
    {"id": "warehouse_fire", "en": "Warehouse fire detected. Evacuate north side.", "sw": "Moto godowni umeonekana. Ondoka upande wa kaskazini.", "cat": "alert", "pri": 3},
    {"id": "server_room_fire", "en": "Server room fire detected. Halon deployed.", "sw": "Moto chumba cha seva umeonekana. Halon imetumwa.", "cat": "alert", "pri": 3},
    {"id": "laundry_fire", "en": "Laundry room fire detected. Electrical hazard.", "sw": "Moto chumba cha usafishaji umeonekana. Hatari ya umeme.", "cat": "alert", "pri": 3},
    {"id": "attic_fire", "en": "Attic fire detected. Roof may be compromised.", "sw": "Moto orubani umeonekana. Paa limeharibika.", "cat": "alert", "pri": 3},
    {"id": "hallway_fire", "en": "Hallway fire detected. Use alternate route.", "sw": "Moto kwayani umeonekana. Tumia njia nyingine.", "cat": "alert", "pri": 3},
    {"id": "stairwell_fire", "en": "Stairwell fire detected. Do not use stairs.", "sw": "Moto ngazini umeonekana. Usitumie ngazi.", "cat": "alert", "pri": 3},
    {"id": "elevator_shaft_fire", "en": "Elevator shaft fire detected. Use stairs only.", "sw": "Moto kwenye shafti ya lifti umeonekana. Tumia ngazi pekee.", "cat": "alert", "pri": 3},
    {"id": "mechanical_room_fire", "en": "Mechanical room fire detected. Hazardous materials.", "sw": "Moto chumba cha mitambo umeonekana. Vifaa hatari.", "cat": "alert", "pri": 3},
    {"id": "electrical_room_fire", "en": "Electrical room fire detected. High voltage risk.", "sw": "Moto chumba cha umeme umeonekana. Hatari ya voltsi kubwa.", "cat": "alert", "pri": 3},
    {"id": "storage_fire", "en": "Storage area fire detected. Contents unknown.", "sw": "Moto eneo la kuhifadhia umeonekana. Vifaa visivyojulikana.", "cat": "alert", "pri": 3},
    {"id": "boiler_room_fire", "en": "Boiler room fire detected. Steam hazard.", "sw": "Moto chumba cha boiler umeonekana. Hatari ya mvuke.", "cat": "alert", "pri": 3},
    {"id": "parking_fire", "en": "Parking structure fire detected. Evacuate vehicles.", "sw": "Moto jengo la magari umeonekana. Ondoa magari.", "cat": "alert", "pri": 3},
    {"id": "roof_fire", "en": "Rooftop fire detected. Fall hazard.", "sw": "Moto paa la jengo umeonekana. Hatari ya kuanguka.", "cat": "alert", "pri": 3},
    {"id": "elevator_lobby_fire", "en": "Elevator lobby fire detected. Use fire exit.", "sw": "Moto ukumbini wa lifti umeonekana. Tumia mlango wa moto.", "cat": "alert", "pri": 3},

    # Risk warnings (41-60)
    {"id": "high_risk_zone", "en": "High fire risk in {zone}. Stay alert.", "sw": "Hatari kubwa ya moto {zone}. Kuwa macho.", "cat": "alert", "pri": 1},
    {"id": "battery_thermal_warning", "en": "Battery thermal runaway risk detected.", "sw": "Hatari ya kukimbia joto la betri imeonekana.", "cat": "alert", "pri": 2},
    {"id": "arc_fault_warning", "en": "Electrical arc fault detected. Fire risk.", "sw": "Kuchomoka kwa umeme umeonekana. Hatari ya moto.", "cat": "alert", "pri": 2},
    {"id": "overheating_warning", "en": "Overheating detected. Fire risk elevated.", "sw": "Joto kupita kiasi umeonekana. Hatari ya moto imeongezeka.", "cat": "alert", "pri": 2},
    {"id": "gas_leak_warning", "en": "Gas leak detected. No open flames.", "sw": "Kuvuja gesi umeonekana. Hakuna moto wazi.", "cat": "alert", "pri": 2},
    {"id": "smoldering_warning", "en": "Smoldering fire detected. Check upholstery.", "sw": "Moto unaoiva umeonekana. Angalia viti.", "cat": "alert", "pri": 2},
    {"id": "dust_explosion_risk", "en": "Dust explosion risk detected in {zone}.", "sw": "Hatari ya mlipuko wa vumbi imeonekana {zone}.", "cat": "alert", "pri": 2},
    {"id": "chemical_fire_risk", "en": "Chemical fire risk detected. Use Class B extinguisher.", "sw": "Hatari ya moto wa kemikali umeonekana. Tumia kizima cha aina B.", "cat": "alert", "pri": 2},
    {"id": "kitchen_grease_risk", "en": "Grease fire risk in kitchen. Keep extinguisher ready.", "sw": "Hatari ya moto wa mafuta jikoni. Weka kizima tayari.", "cat": "alert", "pri": 1},
    {"id": "wildfire_proximity", "en": "Wildfire detected within 10 kilometers. Prepare to evacuate.", "sw": "Moto wa porini umeonekana kilomita 10. Jiandae kuondoka.", "cat": "alert", "pri": 2},
    {"id": "lightning_strike", "en": "Lightning strike detected. Check electrical systems.", "sw": "Kupiga radi umeonekana. Angalia mifumo ya umeme.", "cat": "alert", "pri": 2},
    {"id": "welding_fire_risk", "en": "Welding activity detected. Fire watch required.", "sw": "Shughuli ya kukata umeonekana. Ulinzi wa moto unahitajika.", "cat": "alert", "pri": 1},
    {"id": "hot_work_warning", "en": "Hot work detected in {zone}. Fire watch active.", "sw": "Kazi moto umeonekana {zone}. Ulinzi wa moto unaendelea.", "cat": "alert", "pri": 1},
    {"id": "space_heater_warning", "en": "Space heater proximity alert. Keep clear.", "sw": "Onyo la karibu na kipasha joto. Weka mbali.", "cat": "alert", "pri": 1},
    {"id": "christmas_tree_warning", "en": "Christmas tree heat detected. Check decorations.", "sw": "Joto la mti wa Krismasi umeonekana. Angalia mapambo.", "cat": "alert", "pri": 1},
    {"id": "candle_warning", "en": "Open flame detected near combustibles.", "sw": "Moto wazi umeonekana karibu na vinavyowaka.", "cat": "alert", "pri": 2},
    {"id": "fireworks_warning", "en": "Fireworks activity detected. Fire risk elevated.", "sw": "Shughuli ya maburudisho ya moto umeonekana. Hatari ya moto imeongezeka.", "cat": "alert", "pri": 2},
    {"id": "grilling_warning", "en": "Outdoor grilling detected. Keep fire extinguisher nearby.", "sw": "Kuchoma nje umeonekana. Weka kizima cha moto karibu.", "cat": "alert", "pri": 1},
    {"id": "chimney_fire_risk", "en": "Chimney temperature elevated. Creosote fire risk.", "sw": "Joto la bomba limeongezeka. Hatari ya moto wa creosote.", "cat": "alert", "pri": 1},

    # System status (61-80)
    {"id": "system_armed", "en": "Fire detection system armed and monitoring.", "sw": "Mfumo wa kugundua moto umeamilishwa na unafuatilia.", "cat": "status", "pri": 0},
    {"id": "system_disarmed", "en": "Fire detection system disarmed.", "sw": "Mfumo wa kugundua moto umesitishwa.", "cat": "status", "pri": 0},
    {"id": "sensor_offline", "en": "Sensor {sensor_id} offline. Coverage reduced.", "sw": "Kihisio {sensor_id} hakiko mtandaoni. Ufunikaji umepungua.", "cat": "status", "pri": 1},
    {"id": "sensor_online", "en": "Sensor {sensor_id} back online. Full coverage restored.", "sw": "Kihisio {sensor_id} kimerudi mtandaoni. Ufunikaji umerudishwa.", "cat": "status", "pri": 0},
    {"id": "low_battery", "en": "Low battery on {device}. Replace soon.", "sw": "Betri ndogo kwa {device}. Badilisha hivi karibuni.", "cat": "status", "pri": 1},
    {"id": "battery_critical", "en": "Critical battery on {device}. Immediate replacement required.", "sw": "Betri hatari kwa {device}. Kubadilisha kunahitajika mara moja.", "cat": "status", "pri": 2},
    {"id": "network_lost", "en": "Network connection lost. Local mode active.", "sw": "Muunganisho wa mtandao umepotea. Hali ya mitaa inaendelea.", "cat": "status", "pri": 1},
    {"id": "network_restored", "en": "Network connection restored. Cloud sync resumed.", "sw": "Muunganisho wa mtandao umerudi. Usawazishaji wa wingu umerudi.", "cat": "status", "pri": 0},
    {"id": "daily_test_pass", "en": "Daily system test passed. All systems nominal.", "sw": "Jaribio la kila siku limefaulu. Mifumo yote ni ya kawaida.", "cat": "status", "pri": 0},
    {"id": "daily_test_fail", "en": "Daily system test failed. Check {component}.", "sw": "Jaribio la kila siku limekosa. Angalia {component}.", "cat": "status", "pri": 1},
    {"id": "maintenance_due", "en": "Scheduled maintenance due in {days} days.", "sw": "Matengenezo ya ratiba yanafaa siku {days}.", "cat": "status", "pri": 0},
    {"id": "firmware_updated", "en": "Firmware updated to version {version}.", "sw": "Firmware ime updated kwa toleo {version}.", "cat": "status", "pri": 0},
    {"id": "config_changed", "en": "System configuration updated by {user}.", "sw": "Usanidi wa mfumo ume updated na {user}.", "cat": "status", "pri": 0},
    {"id": "backup_complete", "en": "System backup completed successfully.", "sw": "Backup wa mfumo umekamilika.", "cat": "status", "pri": 0},
    {"id": "backup_failed", "en": "System backup failed. Check storage.", "sw": "Backup wa mfumo umeshindwa. Angalia hifadhi.", "cat": "status", "pri": 1},
    {"id": "tamper_detected", "en": "Tamper detected on {device}. Security alert.", "sw": "Uchokozi umeonekana kwa {device}. Onyo la usalama.", "cat": "status", "pri": 2},
    {"id": "door_forced", "en": "Forced entry detected at {location}.", "sw": "Kuingia kwa nguvu umeonekana {location}.", "cat": "status", "pri": 2},
    {"id": "water_flow_alert", "en": "Water flow detected in suppression system.", "sw": "Maji yanayotiririka umeonekana mfumo wa kuzima moto.", "cat": "status", "pri": 1},
    {"id": "pressure_drop", "en": "Water pressure drop detected in suppression system.", "sw": "Kushuka kwa shinikizo la maji umeonekana mfumo wa kuzima moto.", "cat": "status", "pri": 1},
    {"id": "extinguisher_low", "en": "Fire extinguisher pressure low in {zone}.", "sw": "Shinikizo la kizima cha moto chini {zone}.", "cat": "status", "pri": 1},

    # All-clear and recovery (81-100)
    {"id": "fire_contained", "en": "Fire contained. Remain outside until further notice.", "sw": "Moto umezingirwa. Endelea nje hadi utakapopewa taarifa zaidi.", "cat": "status", "pri": 2},
    {"id": "fire_extinguished", "en": "Fire extinguished. Do not re-enter building.", "sw": "Moto umezimwa. Usiingie tena jengoni.", "cat": "status", "pri": 2},
    {"id": "all_clear", "en": "All clear. Fire department has given clearance to re-enter.", "sw": "Usalama umethibitishwa. Idara ya moto imeruhusu kuingia tena.", "cat": "status", "pri": 2},
    {"id": "partial_all_clear", "en": "Partial all-clear. {zone} safe, other areas restricted.", "sw": "Usalama wa sehemu. {zone} salama, maeneo mengine yamezuiwa.", "cat": "status", "pri": 1},
    {"id": "evacuation_complete", "en": "Evacuation complete. Accounting for personnel.", "sw": "Kutoka kumekamilika. Kuhesabu watu unaendelea.", "cat": "status", "pri": 2},
    {"id": "search_in_progress", "en": "Search and rescue in progress. Stay clear of building.", "sw": "Kutafuta na kuokoa kunaendelea. Weka mbali na jengo.", "cat": "status", "pri": 2},
    {"id": "reentry_approved", "en": "Re-entry approved for {zone}. Use caution.", "sw": "Kuingia tena kimeruhusiwa {zone}. Tumia tahadhari.", "cat": "status", "pri": 1},
    {"id": "elevator_restored", "en": "Elevator service restored. Use with caution.", "sw": "Huduma ya lifti imerudi. Tumia kwa tahadhari.", "cat": "status", "pri": 0},
    {"id": "hvac_restored", "en": "Ventilation system restored. Building air quality normal.", "sw": "Mfumo wa hewa umerudi. Ubora wa hewa wa jengo ni wa kawaida.", "cat": "status", "pri": 0},
    {"id": "suppression_reset", "en": "Fire suppression system reset and ready.", "sw": "Mfumo wa kuzima moto umerudishwa na uko tayari.", "cat": "status", "pri": 0},
    {"id": "drone_recon_complete", "en": "Drone reconnaissance complete. Thermal map available.", "sw": "Uchunguzi wa drone umekamilika. Ramani ya joto inapatikana.", "cat": "status", "pri": 0},
    {"id": "satellite_clear", "en": "Satellite thermal monitoring clear. No active fires.", "sw": "Ufuatiliaji wa joto wa satelite uko safi. Hakuna moto unaotokea.", "cat": "status", "pri": 0},
    {"id": "inspection_scheduled", "en": "Post-fire inspection scheduled for {datetime}.", "sw": "Ukaguzi baada ya moto umepangwa {datetime}.", "cat": "status", "pri": 0},
    {"id": "insurance_notified", "en": "Insurance company notified. Claim number {claim}.", "sw": "Kampuni ya bima imearifiwa. Nambari ya madai {claim}.", "cat": "status", "pri": 0},
    {"id": "air_quality_good", "en": "Air quality index normal. Safe to breathe.", "sw": "Kiwango cha ubora wa hewa cha kawaida. Salama kupumua.", "cat": "status", "pri": 0},
    {"id": "air_quality_poor", "en": "Air quality poor. Use respiratory protection.", "sw": "Ubora wa hewa mbaya. Tumia ulinzi wa kupumua.", "cat": "status", "pri": 1},
    {"id": "debris_warning", "en": "Structural debris hazard. Do not enter.", "sw": "Hatari ya vifaa vya jengo. Usiingie.", "cat": "status", "pri": 2},
    {"id": "asbestos_warning", "en": "Asbestos hazard detected. Respiratory protection required.", "sw": "Hatari ya asbestos umeonekana. Ulinzi wa kupumua unahitajika.", "cat": "status", "pri": 2},
    {"id": "water_damage_alert", "en": "Water damage from suppression. Document for insurance.", "sw": "Uharibifu wa maji kutokana na kuzima. Hifadhi kwa bima.", "cat": "status", "pri": 1},
]


# ── CATEGORY 2: Evacuation Guidance Phrases (100 phrases) ──
# Uses 🔥 Phosphorus personality — clear, warm, guiding

EVACUATION_PHRASES: list[dict] = [
    # Core evacuation commands (1-20)
    {"id": "evacuate_now", "en": "Evacuate the building immediately. Do not stop for belongings.", "sw": "Ondoka jengoni mara moja. Usisimame kwa mali.", "cat": "evacuation", "pri": 3},
    {"id": "evacuate_zone", "en": "Evacuate {zone} immediately. Use nearest exit.", "sw": "Ondoka {zone} mara moja. Tumia mlango wa karibu.", "cat": "evacuation", "pri": 3},
    {"id": "use_stairs", "en": "Use the stairs. Do not use the elevator.", "sw": "Tumia ngazi. Usitumie lifti.", "cat": "evacuation", "pri": 3},
    {"id": "use_exit_north", "en": "Exit through the north door. Proceed to assembly point.", "sw": "Toka kupitia mlango wa kaskazini. Enda kwenye eneo la mkusanyiko.", "cat": "evacuation", "pri": 3},
    {"id": "use_exit_south", "en": "Exit through the south door. Proceed to assembly point.", "sw": "Toka kupitia mlango wa kusini. Enda kwenye eneo la mkusanyiko.", "cat": "evacuation", "pri": 3},
    {"id": "use_exit_east", "en": "Exit through the east door. Proceed to assembly point.", "sw": "Toka kupitia mlango wa mashariki. Enda kwenye eneo la mkusanyiko.", "cat": "evacuation", "pri": 3},
    {"id": "use_exit_west", "en": "Exit through the west door. Proceed to assembly point.", "sw": "Toka kupitia mlango wa magharibi. Enda kwenye eneo la mkusanyiko.", "cat": "evacuation", "pri": 3},
    {"id": "go_to_stairwell_a", "en": "Proceed to Stairwell A. Stay to the right.", "sw": "Enda kwenye Ngazi A. Kaa kulia.", "cat": "evacuation", "pri": 3},
    {"id": "go_to_stairwell_b", "en": "Proceed to Stairwell B. Stay to the right.", "sw": "Enda kwenye Ngazi B. Kaa kulia.", "cat": "evacuation", "pri": 3},
    {"id": "go_to_stairwell_c", "en": "Proceed to Stairwell C. Stay to the right.", "sw": "Enda kwenye Ngazi C. Kaa kulia.", "cat": "evacuation", "pri": 3},
    {"id": "stay_low", "en": "Stay low to the ground. Smoke rises.", "sw": "Kaa chini kwa ardhi. Moshi hupanda.", "cat": "evacuation", "pri": 3},
    {"id": "cover_mouth", "en": "Cover your mouth and nose with a cloth.", "sw": "Funga mdomo na pua kwa kitambaa.", "cat": "evacuation", "pri": 3},
    {"id": "close_doors", "en": "Close all doors behind you as you exit.", "sw": "Funga milango yote nyuma yako unapotoka.", "cat": "evacuation", "pri": 3},
    {"id": "dont_open_hot_door", "en": "Do not open hot doors. Fire is behind.", "sw": "Usifunge milango moto. Moto yuko nyuma.", "cat": "evacuation", "pri": 3},
    {"id": "feel_door", "en": "Feel the door before opening. If hot, find another exit.", "sw": "Hisi mlango kabla ya kufungua. Ikiwa moto, tafuta mlango mwingine.", "cat": "evacuation", "pri": 3},
    {"id": "assembly_point_a", "en": "Proceed to Assembly Point A. North parking lot.", "sw": "Enda kwenye Eneo la Mkusanyiko A. Uwanja wa magari wa kaskazini.", "cat": "evacuation", "pri": 3},
    {"id": "assembly_point_b", "en": "Proceed to Assembly Point B. South lawn.", "sw": "Enda kwenye Eneo la Mkusanyiko B. Uwanja wa kusini.", "cat": "evacuation", "pri": 3},
    {"id": "assembly_point_c", "en": "Proceed to Assembly Point C. East gate.", "sw": "Enda kwenye Eneo la Mkusanyiko C. Lango la mashariki.", "cat": "evacuation", "pri": 3},
    {"id": "help_others", "en": "Help others who need assistance. Do not re-enter.", "sw": "Saidia wengine wanaohitaji msaada. Usiingie tena.", "cat": "evacuation", "pri": 3},
    {"id": "account_for_others", "en": "Account for all family members at assembly point.", "sw": "Weka kumbukumbu ya wanafamilia wote kwenye eneo la mkusanyiko.", "cat": "evacuation", "pri": 3},

    # Room-specific evacuation (21-50)
    {"id": "evac_kitchen", "en": "Leave the kitchen immediately. Grease fire hazard.", "sw": "Ondoka jikoni mara moja. Hatari ya moto wa mafuta.", "cat": "evacuation", "pri": 3},
    {"id": "evac_bedroom", "en": "Leave bedroom through window if door is hot. Use ladder if needed.", "sw": "Ondoka chumbani kupitia dirisha ikiwa mlango ni moto. Tumia ngazi ikiwa unahitaji.", "cat": "evacuation", "pri": 3},
    {"id": "evac_living_room", "en": "Exit living room through front door or patio.", "sw": "Toka chumba cha mapokezi kupitia mlango wa mbele au patio.", "cat": "evacuation", "pri": 3},
    {"id": "evac_bathroom", "en": "Leave bathroom. Wet towels under door if trapped.", "sw": "Ondoka bafuni. Weka taulo maji chini ya mlango ukiwa umenaswa.", "cat": "evacuation", "pri": 3},
    {"id": "evac_office", "en": "Evacuate office. Take stairs, not elevator.", "sw": "Ondoka ofisini. Tumia ngazi, siyo lifti.", "cat": "evacuation", "pri": 3},
    {"id": "evac_conference_room", "en": "Leave conference room. Exit through north hall.", "sw": "Ondoka chumba cha mkutano. Toka kupitia kwaya ya kaskazini.", "cat": "evacuation", "pri": 3},
    {"id": "evac_server_room", "en": "Server room evacuating. Halon discharged. Hold breath.", "sw": "Chumba cha seva kinatoka. Halon imetumwa. Pumua.", "cat": "evacuation", "pri": 3},
    {"id": "evac_garage", "en": "Leave garage. Vehicle fuel risk. Exit to street.", "sw": "Ondoka gerejani. Hatari ya mafuta ya gari. Toka kwenye barabara.", "cat": "evacuation", "pri": 3},
    {"id": "evac_basement", "en": "Basement evacuating. Use Stairwell B to ground floor.", "sw": "Chini ya jengo kinatoka. Tumia Ngazi B hadi sakafu ya chini.", "cat": "evacuation", "pri": 3},
    {"id": "evac_attic", "en": "Attic evacuating. Roof access ladder to exterior.", "sw": "Oruba inatoka. Ngazi ya kuingia paa kwenye nje.", "cat": "evacuation", "pri": 3},
    {"id": "evac_laundry", "en": "Leave laundry room. Lint fire risk.", "sw": "Ondoka chumba cha usafishaji. Hatari ya moto wa manyasi.", "cat": "evacuation", "pri": 3},
    {"id": "evac_storage", "en": "Storage room evacuating. Unknown contents. Avoid.", "sw": "Chumba cha kuhifadhia kinatoka. Vifaa visivyojulikana. Epuka.", "cat": "evacuation", "pri": 3},
    {"id": "evac_pantry", "en": "Leave pantry. Oil and flour dust fire risk.", "sw": "Ondoka stoo. Hatari ya moto wa mafuta na unga.", "cat": "evacuation", "pri": 3},
    {"id": "evac_mechanical", "en": "Mechanical room evacuating. Pressurized systems.", "sw": "Chumba cha mitambo kinatoka. Mifumo yenye shinikizo.", "cat": "evacuation", "pri": 3},
    {"id": "evac_electrical", "en": "Electrical room evacuating. High voltage. Do not touch.", "sw": "Chumba cha umeme kinatoka. Voltsi kubwa. Usiguse.", "cat": "evacuation", "pri": 3},
    {"id": "evac_boiler", "en": "Boiler room evacuating. Steam hazard. Keep distance.", "sw": "Chumba cha boiler kinatoka. Hatari ya mvuke. Weka mbali.", "cat": "evacuation", "pri": 3},
    {"id": "evac_parking", "en": "Parking structure evacuating. Move vehicles to street.", "sw": "Jengo la magari linatoka. Hamisha magari kwenye barabara.", "cat": "evacuation", "pri": 3},
    {"id": "evac_elevator_lobby", "en": "Elevator lobby evacuated. Use Stairwell A.", "sw": "Ukumbi wa lifti umetoka. Tumia Ngazi A.", "cat": "evacuation", "pri": 3},
    {"id": "evac_reception", "en": "Reception area evacuating. Exit to front courtyard.", "sw": "Eneo la mapokezi linatoka. Toka kwenye ua la mbele.", "cat": "evacuation", "pri": 3},
    {"id": "evac_cafeteria", "en": "Cafeteria evacuating. Grease and gas hazard.", "sw": "Cafeteria inatoka. Hatari ya mafuta na gesi.", "cat": "evacuation", "pri": 3},
    {"id": "evac_library", "en": "Library evacuating. Paper fire risk. Move quickly.", "sw": "Maktaba inatoka. Hatari ya moto wa karatasi. Sogea haraka.", "cat": "evacuation", "pri": 3},
    {"id": "evac_gym", "en": "Gymnasium evacuating. Use south emergency exit.", "sw": "Jumba la mazoezi linatoka. Tumia mlango wa dharura wa kusini.", "cat": "evacuation", "pri": 3},
    {"id": "evac_lab", "en": "Laboratory evacuating. Chemical hazard. Avoid fumes.", "sw": "Maabara inatoka. Hatari ya kemikali. Epuka moshi.", "cat": "evacuation", "pri": 3},
    {"id": "evac_classroom", "en": "Classroom {room} evacuating. Form single file line.", "sw": "Chumba cha darasa {room} kinatoka. Shikilia laini moja.", "cat": "evacuation", "pri": 3},
    {"id": "evac_hallway", "en": "Hallway fire. Crawl to nearest exit. Smoke overhead.", "sw": "Moto kwayani. Tata hadi mlango wa karibu. Moshi juu.", "cat": "evacuation", "pri": 3},
    {"id": "evac_stairwell", "en": "Stairwell clear. Descend to ground floor.", "sw": "Ngazi ni safi. Shuka hadi sakafu ya chini.", "cat": "evacuation", "pri": 3},
    {"id": "evac_rooftop", "en": "Rooftop evacuating. Use helicopter landing pad if directed.", "sw": "Paa la jengo linatoka. Tumia eneo la kukodisha helicopta ikiwa umeagizwa.", "cat": "evacuation", "pri": 3},
    {"id": "evac_loading_dock", "en": "Loading dock evacuating. Vehicle traffic hazard.", "sw": "Kiwanja cha kupakia kinatoka. Hatari ya magari.", "cat": "evacuation", "pri": 3},

    # Directional guidance (51-80)
    {"id": "turn_left", "en": "Turn left. Exit ahead.", "sw": "Geuka kushoto. Mlango mbele.", "cat": "evacuation", "pri": 3},
    {"id": "turn_right", "en": "Turn right. Emergency exit.", "sw": "Geuka kulia. Mlango wa dharura.", "cat": "evacuation", "pri": 3},
    {"id": "go_straight", "en": "Go straight ahead. Exit at end of corridor.", "sw": "Enda moja kwa moja. Mlango mwishoni mwa kwaya.", "cat": "evacuation", "pri": 3},
    {"id": "go_upstairs", "en": "Go up one flight to roof exit.", "sw": "Panda gorofa moja hadi mlango wa paa.", "cat": "evacuation", "pri": 3},
    {"id": "go_downstairs", "en": "Go down to ground floor. Do not stop.", "sw": "Shuka hadi sakafu ya chini. Usisimame.", "cat": "evacuation", "pri": 3},
    {"id": "follow_corridor", "en": "Follow corridor to end. Exit on left.", "sw": "Fuata kwaya hadi mwisho. Mlango kushoto.", "cat": "evacuation", "pri": 3},
    {"id": "past_reception", "en": "Go past reception desk. Exit behind.", "sw": "Pita dawati la mapokezi. Mlango nyuma.", "cat": "evacuation", "pri": 3},
    {"id": "through_double_doors", "en": "Go through double doors. Assembly point outside.", "sw": "Pitia milango mibili. Eneo la mkusanyiko nje.", "cat": "evacuation", "pri": 3},
    {"id": "down_ramp", "en": "Use wheelchair ramp to exit. Careful on slope.", "sw": "Tumia mteremko wa kiti cha magurudumu kutoka. Tahadhari kwenye mteremko.", "cat": "evacuation", "pri": 3},
    {"id": "through_garden", "en": "Exit through garden gate. Assembly point on lawn.", "sw": "Toka kupitia lango la bustani. Eneo la mkusanyiko uwanjani.", "cat": "evacuation", "pri": 3},
    {"id": "to_parking_lot", "en": "Proceed to parking lot. Account for vehicles.", "sw": "Enda kwenye uwanja wa magari. Weka kumbukumbu ya magari.", "cat": "evacuation", "pri": 3},
    {"id": "to_sidewalk", "en": "Move to sidewalk. Stay clear of building entrance.", "sw": "Hamisha kwenye barabara ya watembezi. Weka mbali na mlango wa jengo.", "cat": "evacuation", "pri": 3},
    {"id": "to_opposite_side", "en": "Move to opposite side of street. Debris risk.", "sw": "Hamisha upande mwingine wa barabara. Hatari ya vifaa.", "cat": "evacuation", "pri": 3},
    {"id": "away_from_windows", "en": "Move away from windows. Glass may shatter.", "sw": "Hamisha mbali na madirisha. Kioo vinaweza kuvunjika.", "cat": "evacuation", "pri": 3},
    {"id": "away_from_elevator", "en": "Move away from elevator bank. Use stairs.", "sw": "Hamisha mbali na lifti. Tumia ngazi.", "cat": "evacuation", "pri": 3},
    {"id": "to_stairwell_a", "en": "Stairwell A is clear. Go now.", "sw": "Ngazi A ni safi. Enda sasa.", "cat": "evacuation", "pri": 3},
    {"id": "to_stairwell_b", "en": "Stairwell B is clear. Go now.", "sw": "Ngazi B ni safi. Enda sasa.", "cat": "evacuation", "pri": 3},
    {"id": "avoid_stairwell_c", "en": "Avoid Stairwell C. Smoke detected.", "sw": "Epuka Ngazi C. Moshi umeonekana.", "cat": "evacuation", "pri": 3},
    {"id": "use_alternate_route", "en": "Main exit blocked. Use alternate route through {zone}.", "sw": "Mlango kuu umezuiwa. Tumia njia nyingine kupitia {zone}.", "cat": "evacuation", "pri": 3},
    {"id": "follow_green_lights", "en": "Follow green exit lights to safety.", "sw": "Fuata taa za kijani za kutoka hadi usalama.", "cat": "evacuation", "pri": 3},
    {"id": "follow_floor_lights", "en": "Follow floor lighting to nearest exit.", "sw": "Fuata mwanga wa sakafu hadi mlango wa karibu.", "cat": "evacuation", "pri": 3},
    {"id": "stay_in_room", "en": "Stay in room. Seal door with wet towels. Signal window.", "sw": "Kaa chumbani. Funga mlango kwa taulo maji. Toa ishara dirishani.", "cat": "evacuation", "pri": 3},
    {"id": "wait_for_rescue", "en": "Fire department is on site. Stay visible at window.", "sw": "Idara ya moto iko hapa. Kaa unaonekana dirishani.", "cat": "evacuation", "pri": 3},
    {"id": "dont_jump", "en": "Do not jump. Await rescue ladder.", "sw": "Usiruke. Subiri ngazi ya kuokolea.", "cat": "evacuation", "pri": 3},
    {"id": "break_window_if_needed", "en": "If trapped, break window with heavy object. Signal outside.", "sw": "Ukiwa umenaswa, vunja dirisha kwa kitu kizito. Toa ishara nje.", "cat": "evacuation", "pri": 3},
    {"id": "use_fire_escape", "en": "Deploy fire escape ladder from window. Careful.", "sw": "Tumia ngazi ya kukimbia moto kutoka dirishani. Tahadhari.", "cat": "evacuation", "pri": 3},
    {"id": "roof_access", "en": "Roof access available. Await helicopter rescue.", "sw": "Kuingia paa kunapatikana. Subiri kuokolewa na helicopta.", "cat": "evacuation", "pri": 3},
    {"id": "garage_exit", "en": "Exit through garage door to alley. Move quickly.", "sw": "Toka kupitia mlango wa gerejani hadi kijito. Sogea haraka.", "cat": "evacuation", "pri": 3},
    {"id": "loading_bay_exit", "en": "Exit through loading bay. Watch for trucks.", "sw": "Toka kupitia kiwanja cha kupakia. Angalia malori.", "cat": "evacuation", "pri": 3},

    # Risk-specific guidance (81-100)
    {"id": "avoid_kitchen", "en": "Avoid kitchen area. Grease fire. Use east exit.", "sw": "Epuka eneo la jikoni. Moto wa mafuta. Tumia mlango wa mashariki.", "cat": "evacuation", "pri": 3},
    {"id": "avoid_electrical", "en": "Avoid electrical room. Shock hazard. Use north stairs.", "sw": "Epuka chumba cha umeme. Hatari ya moto. Tumia ngazi za kaskazini.", "cat": "evacuation", "pri": 3},
    {"id": "avoid_chemical_storage", "en": "Avoid chemical storage. Toxic fumes. Use west exit.", "sw": "Epuka hifadhi ya kemikali. Moshi hatari. Tumia mlango wa magharibi.", "cat": "evacuation", "pri": 3},
    {"id": "avoid_boiler", "en": "Avoid boiler room. Steam burns. Use south stairs.", "sw": "Epuka chumba cha boiler. Joto la mvuke. Tumia ngazi za kusini.", "cat": "evacuation", "pri": 3},
    {"id": "avoid_parking_level", "en": "Avoid parking level {level}. Vehicle fuel risk.", "sw": "Epuka kiwango cha magari {level}. Hatari ya mafuta ya gari.", "cat": "evacuation", "pri": 3},
    {"id": "avoid_elevator_shaft", "en": "Stay away from elevator shaft. Smoke channel.", "sw": "Kaa mbali na shafti ya lifti. Kwaya ya moshi.", "cat": "evacuation", "pri": 3},
    {"id": "use_wheelchair_exit", "en": "Wheelchair users use east ramp. Staff assistance available.", "sw": "Watumiaji wa viti vya magurudumu tumia mteremko wa mashariki. Msaada wa wafanyakazi unapatikana.", "cat": "evacuation", "pri": 3},
    {"id": "assistance_needed", "en": "If you need assistance, proceed to Stairwell A. Staff will help.", "sw": "Ukiwa unahitaji msaada, enda kwenye Ngazi A. Wafanyakazi watasaidia.", "cat": "evacuation", "pri": 3},
    {"id": "deaf_assistance", "en": "Strobe lights indicate evacuation route. Follow flashing lights.", "sw": "Taa za strobe zinaonyesha njia ya kutoka. Fuata taa zinazomulika.", "cat": "evacuation", "pri": 3},
    {"id": "blind_assistance", "en": "Audio guidance active. Follow voice directions.", "sw": "Mwongozo wa sauti unaendelea. Fuata maelekezo ya sauti.", "cat": "evacuation", "pri": 3},
    {"id": "children_first", "en": "Children proceed first to Assembly Point B. Teachers follow.", "sw": "Watoto waendelee kwanza kwenye Eneo la Mkusanyiko B. Walimu wafuate.", "cat": "evacuation", "pri": 3},
    {"id": "elderly_assistance", "en": "Elderly and mobility-impaired proceed to Stairwell C. Elevator available.", "sw": "Wazee na wale wa kutembea kwa shida waendelee kwenye Ngazi C. Lifti inapatikana.", "cat": "evacuation", "pri": 3},
    {"id": "pets_prohibited", "en": "Do not return for pets. Firefighters will search for animals.", "sw": "Usirudi kwa wanyama. Wazima moto watawatafuta wanyama.", "cat": "evacuation", "pri": 3},
    {"id": "stay_at_assembly", "en": "Remain at assembly point. Do not leave until accounted for.", "sw": "Kaa kwenye eneo la mkusanyiko. Usiondoke hadi kuhesabiwa.", "cat": "evacuation", "pri": 3},
    {"id": "await_all_clear", "en": "Await all-clear from fire department. Do not re-enter.", "sw": "Subiri usalama kutoka kwa idara ya moto. Usiingie tena.", "cat": "evacuation", "pri": 3},
    {"id": "firefighter_incoming", "en": "Firefighters entering building. Clear all entrances.", "sw": "Wazima moto wanaingia jengoni. Weka safi milango yote.", "cat": "evacuation", "pri": 3},
    {"id": "drone_overhead", "en": "Fire department drone overhead. Stay visible.", "sw": "Drone ya idara ya moto juu. Kaa unaonekana.", "cat": "evacuation", "pri": 2},
    {"id": "water_drop_warning", "en": "Water drop from aerial suppression imminent. Move to covered area.", "sw": "Maji kushuka kutoka kwa kuzima hewani yanakaribia. Hamisha kwenye eneo lililofunikwa.", "cat": "evacuation", "pri": 2},
    {"id": "ventilation_warning", "en": "Positive pressure ventilation starting. Stand clear of vents.", "sw": "Uvuvio wa shinikizo chanya unaanza. Kaa mbali na vifaa vya hewa.", "cat": "evacuation", "pri": 2},
]


def initialize_phrase_database(db_path: str | None = None) -> None:
    """Create and populate the phrase database.

    Args:
        db_path: Path to SQLite database. Defaults to ~/.fire_suppression/audio_phrases.db
    """
    from fire_suppression.alerts.audio_keep_alive import PhraseCache

    cache = PhraseCache(db_path=db_path, mock=False)

    # Add all fire alert phrases
    for phrase in FIRE_ALERT_PHRASES:
        cache.add_phrase(
            phrase_id=phrase["id"],
            category=phrase["cat"],
            en_text=phrase["en"],
            sw_text=phrase["sw"],
            priority=phrase["pri"],
        )

    # Add all evacuation phrases
    for phrase in EVACUATION_PHRASES:
        cache.add_phrase(
            phrase_id=phrase["id"],
            category=phrase["cat"],
            en_text=phrase["en"],
            sw_text=phrase["sw"],
            priority=phrase["pri"],
        )

    print(f"Initialized {len(FIRE_ALERT_PHRASES) + len(EVACUATION_PHRASES)} phrases")
    print(f"Database: {cache._db_path}")
    stats = cache.to_dict()
    print(f"By category: {stats['by_category']}")


if __name__ == "__main__":
    initialize_phrase_database()
