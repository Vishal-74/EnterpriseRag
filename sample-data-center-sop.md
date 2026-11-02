# Standard Operating Procedure: Apex Quantum Facility (Hall C)

**Document ID:** SOP-ENG-2026-C  
**Version:** 3.4  
**Effective Date:** 15 October 2026  
**Lead Systems Engineer:** Dr. Sarah Vance (Badge: ENG-8802)  
**Emergency Bridge Extension:** 5520  

---

## 1. Primary Power and Backup Generators

1. The primary incoming electrical feed delivers 11 kV from the local grid substation.
2. In the event of grid brownout or blackout, emergency backup power is supplied by three **Cummins QSK95-G10** diesel generators rated at **3500 kVA** each.
3. Generator fuel reserves must remain at a minimum of **85% capacity** at all times, providing 72 hours of continuous full-load runtime.
4. Routine generator load bank testing takes place on the **first Tuesday of every month at 03:00 UTC**.

---

## 2. Server Hall Cooling & Thermal Thresholds

1. Hall C houses high-density liquid-cooled server racks.
2. The circulating coolant mixture is **Glycol-X 40/60** (40% inhibited propylene glycol, 60% demineralized water).
3. The coolant system flush and refill cycle must be performed **every 45 days**.
4. The nominal server operating temperature range is **18.5°C to 22.0°C**.
5. If any thermal sensor exceeds **24.5°C**, an amber advisory is automatically sent to the on-call engineer.
6. If server rack inlet temperatures breach **28.0°C**, the emergency shutdown sequence **BLUE-NEBULA-9** is initiated immediately.

---

## 3. Physical Access and Security Protocols

1. All personnel entering Hall C must swipe an authorized biometric badge and pass through the anti-tailgating mantrap (Door M-3).
2. Unaccompanied visitor access is strictly prohibited. All vendors must be escorted by an engineer with Level 3 clearance.
3. Access logs are stored in encrypted format and retained for **365 days** in compliance with the Site Security Charter.

