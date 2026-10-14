# Current school IPR DOCX and portal form

The teacher DOCX and the observed **“Створення ІПР для ЗЗСО”** portal page both use the 11-section 2026 layout. The older completed PDF uses a 13-section layout and is documented separately in [the historical comparison](portal_pdf_to_teacher_docx_matrix.md). This file contains no child data.

| Teacher DOCX | Current portal control | Chrome extension action |
| --- | --- | --- |
| §1 period; §2 class, study year, phones, address, enrollment date | Named inputs and address textarea | Fill populated values |
| §2 child full name | Displayed text | Verify identity before editing |
| §3 needs and support description | `3[1][1]` | Fill when present |
| §4 protocol date, number, support level | `protocol_*`, `supportLevel` | Fill when the date and one support level are explicit |
| §5 environment and learning adaptations | `5[1][1]`–`5[25][1]` | Match row labels, fill populated notes |
| §5 individual plan, schedule, learning aids | `5[26]`–`5[28]` | Set explicit choices and details |
| §5 adapted or modified subjects | `5[29+]` | Add rows and fill named columns |
| §6 goals and expected results | `6[1+]` | Add rows and fill populated columns |
| §7 additional lessons and services | `7[1+]` | Add rows and fill populated columns |
| §8 assessment choices | `8[1]`–`8[9]` | Check or uncheck each explicit DOCX choice |
| §9 extension of study | `9[1][1]` | Set only when exactly one choice is marked |
| §10 team members | `10[1+]` | Add rows and fill named columns |
| §11 parent agreement | `footer_parents_names` | Fill only when the signer matches a listed parent |

For the supplied example, the local extractor finds **123 populated controls**. This counts individual inputs, including table cells. Blank and unclear DOCX entries are left for review. The extension validates control type, available select value, and labeled adaptation row before filling, then reads back the edited values. It leaves the form open for review and does not press **Сформувати документ**.

The **Copy fields for normal browser** fallback remains a four-field copy guide. The wider mapping is used by the paired Chrome extension and in the local preview count.
