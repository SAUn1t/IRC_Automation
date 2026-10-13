# School IPR DOCX and portal form compatibility

The supplied DOCX follows an 11-section school IPR layout. The portal page opened through “Створити ІПР” shows a different 13-section form. This report describes structure only; no document values are stored here.

| DOCX content | Portal counterpart | Current handling |
| --- | --- | --- |
| Execution period | `execution_period` | Filled and verified |
| Year of study | `year_of_study` | Filled and verified |
| Class | `child_grade` | Filled and verified |
| Parent contact numbers | `parents_phones` | Filled and verified |
| Child full name | Displayed in the portal form | Checked for identity; not edited |
| Support level and educational needs | Recommendation and individual development fields use different wording | Manual review |
| Environment adaptations and modifications | Section 4 has a different set of choices and required notes | Manual review |
| Subject-specific goals and outcomes | Portal sections 3 and 12 organize goals differently | Manual review |
| Additional services and support team tables | Similar tables, with dynamic row controls | Manual review until row behavior is verified |
| Assessment, extension of study, and parent agreement | Related portal controls and text | Manual review until semantics and choices are verified |

`manual_review_only: true` keeps the browser open after the four mapped fields pass read-back verification. The app does not use the portal's final action in this mode. The user must review and complete every remaining section and decide whether to generate the document in the browser.
