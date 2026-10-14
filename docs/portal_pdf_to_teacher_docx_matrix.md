# Portal IPR PDF ↔ teacher DOCX field matrix

This historical comparison covers the supplied **13-section portal PDF (2025–2026)** and **11-section teacher DOCX (2026–2027)**. The current “Створення ІПР для ЗЗСО” HTML is an **11-section form** and is mapped separately in [current template compatibility](template_compatibility.md). The PDF is a completed prior-year IPR, so its values are evidence of the old output layout, **not** values to copy into the new form. This file records field locations and transfer rules, without personal values.

**Legend:** `Exact` = same meaning and a uniquely readable DOCX value; `Conditional` = an analog exists, but a choice, note, or transformation needs confirmation; `Manual` = related content, but not equivalent; `Absent` = no DOCX source. Only `Exact` fields may be filled automatically, followed by read-back and manual review. Blank choices remain blank; they must never be interpreted as “Ні”.

## Sections 1–3: identity and individual characteristics

| PDF destination / portal control | Teacher DOCX source | Match | Transfer rule |
| --- | --- | --- | --- |
| 1. Період виконання / `execution_period` | §1 “Період виконання” | Exact | Use the DOCX period for the new school year. |
| 2. Child full name / displayed text | §2 child name | Exact | Verify portal identity; the field is not editable on this form. |
| 2. Birth date / displayed text | §2 birth date | Exact | Verify identity; do not edit. |
| 2. School / displayed text | §2 full school name | Exact | Verify displayed school; allow only harmless typography differences. |
| 2. Year of study / `year_of_study` | §2 “рік навчання” | Exact | Select the matching numeric option. |
| 2. Class / `child_grade` | §2 “клас навчання” | Exact | Copy the DOCX class. |
| 2. Parent contact numbers / `parents_phones` | §2 parent contact numbers | Exact | Copy as printed; no fallback to the old PDF. |
| 3. Current competencies / `3[1][1]` | §6 table, “Наявні знання, вміння і навички” per subject | Manual | The PDF has one general cell; the DOCX has eight subject/service rows. It needs a human-authored synthesis or an explicitly approved subject-labelled concatenation. |
| 3. Educational difficulties / `3[1][2]` | §3 categories and degree of needs; some §6 current-skill descriptions | Manual | The diagnosis category/degree is not the detailed difficulties narrative shown in the PDF. |
| 3. Needs / `3[1][3]` | §6 goals and tasks per subject | Manual | Goals are related to needs but do not assert the same thing. |

The DOCX also has parent name, address, and admission date in §2. The old portal form has no matching editable fields for address or admission date. Parent name has a separate footer destination described below.

The PDF has the previous year's class and period. The DOCX specifies a later class and period. The same child identity and phone number in both files do not make the PDF a current-year source.

## Section 4.1–4.2: support and environment table

| PDF destination / portal control | Teacher DOCX source | Match | Transfer rule |
| --- | --- | --- | --- |
| Recommended support level / `supportLevel` | §3 IRC categories/degree; §4 team-selected support level | Manual | **Recommended** level and **team-determined** level have different sources. The DOCX does not explicitly state the IRC recommendation as a numeric level. Do not derive it from “IV ступінь”. |
| Accessibility / `4[1][0]`, note `4[1][1]` | §5 adaptation table “Доступність” | Exact for “Ні”; conditional otherwise | An explicit “Ні” maps to No. A Yes needs a concrete note. |
| Lighting / `4[2][0..1]` | §5 “Освітлення” | Conditional | Descriptive adequate lighting does not itself establish whether an adaptation is required. |
| Noise / `4[3][0..1]` | §5 “Рівень шуму” | Conditional | A noise-minimization measure suggests an adaptation, but the DOCX lacks an explicit Yes/No. |
| Solitude / `4[4][0..1]` | §5 “Потреба в усамітненні...” | Exact when explicit | Split an explicit “Так, ...” into Yes and the remaining note. |
| Visual schedule / `4[5][0..1]` | §5 “використання візуального розкладу” | Exact for “Ні”; conditional for Yes | A Yes also needs a note, which the DOCX row may omit. |
| Extra task time / `4[6][0..1]` | §5 “збільшення часу на виконання завдань” | Conditional | The DOCX gives Yes, but no portal-required note. DOCX §8 assessment timing is a different context. |
| More assistance / `4[7][0..1]` | §5 “збільшення обсягу допомоги...” | Conditional | The DOCX gives Yes, but no specific note. |
| Movement regime / `4[8][0..1]` | §5 “чергування видів діяльності” | Manual | Alternating activities is not necessarily a movement regime. |
| Rewards / `4[9][0..1]` | §5 “використання заохочень” | Conditional | The DOCX gives Yes, but no description of the rewards. |
| Concentration aids / `4[10][0..1]` | §5 “використання засобів концентрації уваги” | Conditional | The DOCX gives Yes, but no description of the aids. |
| Other pedagogic adaptation / `4[11][0..1]` | §5 adaptation “інше”; environment “Інше” | Manual | Two different “other” rows; do not choose one by position alone. |
| Hint/instruction cards / `4[12][0..1]` | §5 “картки-підказки, картки-інструкції”; “Інформаційні позначки” | Conditional | Yes is explicit, but the portal note needs review. |
| Alternative communication / `4[13][0..1]` | §5 alternative-communication rows (gesture, Braille, calendar, PECS, other) | Manual | The broad portal item cannot be inferred from individual listed choices without checking all options and the meaning of “other”. |
| Other material adaptation / `4[14][0..1]` | §5 adaptation “інше” | Conditional | Use only an explicit, populated value attributable to material adaptation. |
| Reduced subject content / `4[15][0..1]` | §5 modification “зміна змісту навчальних предметів” | Manual | A change in content is broader than a reduction. An explicit No to any change supports No to reduction, but should be reviewed. |
| Lower task demands / `4[16][0..1]` | §5 “зміна вимог щодо виконання завдань” | Manual | A change in requirements is broader than lowering them. |
| Other modification / `4[17][0..1]` | §5 modification “інше”; monitoring approach | Manual | No unique equivalent. |

The portal HTML defaults many of these rows to **Так** and makes their notes required. These defaults do not represent the DOCX. Each radio and required note needs an explicit decision; leaving default Yes could create false information or block submission.

The DOCX has no dedicated old-form rows for information signs, furniture, individual markers, alternating activities, changed monitoring, calendar system, or PECS. Some may be described in another portal note after human review, but none should be silently dropped or forced into an unrelated old-form field.

## Section 4.3–4.6: special services, consultations, plan

| PDF destination / portal control | Teacher DOCX source | Match | Transfer rule |
| --- | --- | --- | --- |
| Sign language and/or interpreter / `4[18][0]` | §5 “Жестова мова” | Conditional | Sign-language choice is related; interpreter need is not separately stated. |
| Braille / `4[19][0]` | §5 “Шрифт Брайля” | Exact | Copy an explicit checked/unchecked choice. |
| Additional classes / `4[20][0]` | §7 additional services table | Conditional | Populated service rows support Yes, but there is no explicit Yes/No choice. |
| IRC consultation / `4[21][0]` | No consultation decision; IRC specialist in §10 team table is different | Absent | Manual decision. |
| Special-school consultation / `4[22][0]` | None | Absent | Manual decision. |
| Other consultation / `4[23][0..1]` | None | Absent | Manual decision and required specialist note if Yes. |
| Individual curriculum Yes/No / `4[24][0]` | §5 “наявність індивідуального навчального плану” | Exact value, **source conflict** | DOCX explicitly marks No but still lists subjects requiring adaptation below. Do not decide how the portal should handle this contradiction automatically. |
| Subject, adaptation/modification, responsible teacher / dynamic `4[25+][1..3]` | §5 subject table | Conditional | Three columns match, but the DOCX's “No individual plan” conflicts with the portal's conditional table. Resolve the plan status before transferring any rows. |

## Sections 5–9: services, schedule, assistant, resources

| PDF destination / portal control | Teacher DOCX source | Match | Transfer rule |
| --- | --- | --- | --- |
| 5. Service name / dynamic `5[n][1]` | §7 service table, column 1 | Exact | Preserve all current-year rows. |
| 5. Specialist / `5[n][2]` | §7 table, column 2 | Exact | Use the DOCX name, including if the portal's specialist dropdown lacks it. |
| 5. Location / `5[n][3]` | No location column in §7 | Absent | Manual entry; never copy last year's room number from the PDF. |
| 5. Schedule / `5[n][4]` | §7 day and time columns | Conditional | Combine corresponding day/time lines only if their counts and order clearly align. |
| 6. Learning schedule / `6[1][1]`, detail `6[2][1]` | §5 “здійснення освітнього процесу” | Exact for class schedule | If adaptive schedule is selected, its individual-lesson detail needs an explicit source. |
| 7. Student assistant needed / `7[1][1]` | None | Absent | A **teacher assistant** appearing in §10 team members does not answer whether a **student assistant** is needed. |
| 7. Parent, other representative, authorized person, social worker / `7[2..5]` | No corresponding assistant-role choices | Absent | Manual decisions and names. Do not copy the parent's name merely because it exists in §2. |
| 8. Three textbook/material checkboxes / `8[1][1..3]` | None | Absent | Manual decisions. |
| 8. Auxiliary learning aids Yes/No and list / `8[2][0..1]` | §5 “забезпечення допоміжними засобами для навчання” and list | Exact when explicit | Respect the Yes/No choice; a blank list with No does not become Yes because adaptations elsewhere mention cards. |
| 9. Reasonable accommodation Yes/No and list / `9[1][0..1]` | §5 “розумне пристосування” heading and adaptation table | Manual | The DOCX gives several measures, not one unambiguous yes/no plus list. Prepare a reviewed summary if needed. |

## Sections 10–13 and agreement

| PDF destination / portal control | Teacher DOCX source | Match | Transfer rule |
| --- | --- | --- | --- |
| 10. Timing/content assessment adaptation / `10[1][1]` | §8 choices on flexible time, fewer tasks, optimal forms, simplified instructions | Conditional | One old checkbox combines several newer choices. Do not check it from only one broad keyword. |
| 10. Accessible presentation / `10[2][1]` | §8 “використання доступних форм викладу інформації” | Exact choice | Copy the explicit checkbox state. |
| 10. Separate task cards/adapted materials / `10[3][1]` | §8 simplified instructions/cards; §5 card adaptations | Conditional | Related but not identical to separate assessment cards. |
| 10. Adjust for perception / `10[4][1]` | §8 avoidance of graphic tasks and visual/auditory stimuli | Conditional | The old checkbox merges two newer choices. |
| 10. Other and note / `10[5][0..1]` | §8 “інше” | Exact only when explicit | If checked, a nonblank description is required. |
| 11. Extend period of study / `11[1][1]` | §9 end-of-year Yes/No | Exact **only if selected** | Both choices are blank in this DOCX. Leave unresolved; do not inherit last year's No. |
| 12. Intellectual goals/results / `12[1][1..3]` | §6 mathematics and psychology rows | Manual | Subject rows cannot be uniquely merged into one development-sphere row. |
| 12. Sensory/motor / `12[2][1..3]` | Scattered §6 descriptions, no dedicated row | Manual | Needs synthesis. |
| 12. Speech / `12[3][1..3]` | §6 language, reading, speech-development rows | Manual | Multiple candidate rows. |
| 12. Physical / `12[4][1..3]` | No dedicated §6 physical-development row | Absent | Manual decision. |
| 12. Emotional/volitional / `12[5][1..3]` | §6 defectology and psychology rows | Manual | Multiple candidate rows. |
| 12. Social / `12[6][1..3]` | §6 world studies, defectology, psychology rows | Manual | Multiple candidate rows. |
| 12. Learning difficulties / `12[7][1..3]` | §6 several subject rows | Manual | Multiple candidate rows. |
| 12. Other / `12[8][1..3]` | No dedicated source | Absent | Manual decision. |
| 13. Team names and roles / dynamic `13[n][1..2]` | §10 team table, columns 1–2 | Exact | Transfer current-year members only; signatures remain for humans. |
| Parent agreeing to IPR / `footer_parents_names` | §11 named agreeing parent; compare §2 parent name | Exact if consistent | Use the §11 signer, not every parent or every team member. Mismatch with §2 needs review. |
| Signature and date | §11 signature/date blanks; portal prints signature line and date | Manual | No electronic signature is supplied by this DOCX. |

The third column of the portal §12 table is **expected** results; its fourth column is **achieved** results after execution. The DOCX §6 has the same distinction within each subject row. The old PDF contains achieved results from 2025–2026; the current-year DOCX's achieved-result cells are blank. Never carry historical achieved results into a new IPR.

## Material differences observed in these two files

| Topic | Completed PDF | Current teacher DOCX | Required action |
| --- | --- | --- | --- |
| School year and class | Prior period/class | Later period/class | Use the DOCX; verify portal identity. |
| Individual learning plan | Yes | Explicit No, yet subject adaptation rows exist | Resolve the DOCX's internal inconsistency before touching `4[24]` or its rows. |
| Auxiliary learning aids | A populated list | Explicit No with an empty list | Use current-year decision; verify that the school intended No. |
| Additional services | Room, specialist, and prior timetable | Specialist and new timetable, no room | Obtain current-year locations from a teacher. |
| Achieved development results | Filled for prior year | Current-year achieved-result cells empty | Do not copy historical outcomes. |
| Team membership | Prior-year members | Current-year members | Use the DOCX team and review signatures separately. |

The DOCX school letterhead, director approval, parent address, admission date, some adaptation categories, and detailed per-subject goals have no one-to-one destination in the old portal form. They remain in the DOCX and require human review of the final generated document.

## Implementation boundary

The current app already fills and verifies the four editable exact scalar fields in §§1–2. A later implementation can add other `Exact` fields if it reads DOCX tables and checkbox marks reliably, controls dynamic portal rows, verifies every changed control, and presents the unresolved fields above for review. The form's **“Сформувати документ”** action must remain unavailable to automation until every required field is resolved and a real success signal is verified.
