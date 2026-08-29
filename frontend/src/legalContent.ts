export type LegalSection = {
  title: string;
  paragraphs: string[];
  bullets?: string[];
};

export const LEGAL_VERSION = "1.0";
export const LEGAL_EFFECTIVE_DATE = "To be confirmed";

export const TERMS_INTRO =
  "Please read these Terms of Use before you use Rehyn. They are a legal agreement between you and Rehyn Ltd. Section 2 contains important safety information, and section 7 explains how Rehyn uses information to improve its technology. If you do not accept these Terms, do not use the Services.";

export const TERMS_SECTIONS: LegalSection[] = [
  {
    title: "1. Who we are and what these Terms cover",
    paragraphs: [
      'Rehyn Ltd, a company incorporated in England and Wales with company number 17417716 and registered office at [address], operates the Rehyn mobile application, website and connected features (together, the "Services"). Rehyn is referred to in these Terms as "Rehyn", "we" or "us", and the person using the Services is referred to as "you".',
      "These Terms of Use, together with the Rehyn Privacy Notice, govern your access to and use of the Services. By creating an account or otherwise using the Services, you confirm that you accept these Terms and that you are legally able to do so.",
      "The Services are currently provided free of charge as an early release. Some features are still in development, may change or be withdrawn, and may not perform with the accuracy or reliability of a finished product.",
      "The Services are intended for people aged 18 or over.",
    ],
  },
  {
    title: "2. Important safety information",
    paragraphs: [
      "Rehyn provides digital rehabilitation support. It does not provide emergency care, make a medical diagnosis, or guarantee a particular recovery outcome.",
      "Rehyn does not replace your doctor, therapist or other qualified healthcare professional. Follow their advice. If Rehyn conflicts with their advice, follow the professional advice and contact info@rehyn.com.",
      "Before starting a new or more demanding activity, confirm with a qualified healthcare professional that it is appropriate for you.",
      "Use Rehyn in a safe space with a clear floor, suitable footwear and your usual support or walking aid. Stop and seek advice if you experience pain, dizziness, breathlessness, chest discomfort, sudden weakness or numbness, confusion, speech difficulty, loss of balance, a fall, or anything else that concerns you.",
      "If you think you may be having a stroke or another medical emergency, call 999 in the UK or your local emergency number. Do not request urgent help through Rehyn. The Services are not monitored in real time.",
    ],
  },
  {
    title: "3. Your account",
    paragraphs: [
      "You must provide accurate, current and complete information and take reasonable steps to keep your account secure.",
      "Do not share your account credentials. Tell us promptly if you believe someone has accessed your account without permission.",
      "A family member, carer or other helper may assist you only if you are comfortable with that and they follow these Terms. You remain responsible for activity on your account.",
    ],
  },
  {
    title: "4. Using Rehyn responsibly",
    paragraphs: ["You must not:"],
    bullets: [
      "Use the Services in a way that is unsafe, beyond your ability, or against professional advice.",
      "Upload unlawful, harmful or misleading material, or record another person without their knowledge and agreement.",
      "Use the Services on another person's behalf unless they understand and agree.",
      "Reverse engineer, scrape or attempt to extract Rehyn's models, source code or protected technology.",
      "Interfere with, overload, probe or gain unauthorised access to the Services.",
      "Use the Services for a commercial or competing purpose without our written permission.",
    ],
  },
  {
    title: "5. Your content and the rights you give us",
    paragraphs: [
      "Your content may include movement videos, assessment answers, goals, activity records, messages and feedback. You keep ownership of it.",
      "You give Rehyn a non-exclusive, worldwide, royalty-free licence to host, store, process, analyse and display your content only as needed to operate the Services, generate measurements and plans, show progress, provide support, maintain security and comply with law. This licence lasts while we lawfully hold the content.",
      "This licence does not permit model training. Model training requires the separate choice described in section 7.",
      "Movement videos are processed and then deleted as described in the Privacy Notice. Derived movement measurements may be retained.",
      "You must have the right to provide your content. Any identifiable person appearing in a recording must know about and agree to the recording.",
    ],
  },
  {
    title: "6. Automated guidance and Alira",
    paragraphs: [
      "Rehyn uses automated systems, including Alira, to generate movement measurements, rehabilitation plans, prompts, summaries and other guidance.",
      "Automated guidance is supportive only. It may be incomplete, inaccurate or unsuitable for your circumstances. It is not a clinical recommendation, and you should use your judgement and follow professional advice.",
      "Alira is software, not a clinician, supervisor or emergency service.",
      "Rehyn does not currently make legal or similarly significant decisions about you solely by automated means. We will tell you if that changes.",
    ],
  },
  {
    title: "7. Using information to improve Rehyn",
    paragraphs: [
      "Rehyn is an early-release service and we want to improve its accuracy and reliability transparently.",
      "Health, rehabilitation and functional information is sensitive. We will use it to train, test or evaluate Rehyn's technology only if you give separate, explicit consent through the app's Help improve Rehyn control. Accepting these Terms is not that consent.",
      "You may withdraw that consent at any time in Settings or by emailing info@rehyn.com. Withdrawal stops future use for that purpose and does not affect other lawful processing.",
      "Your access and features remain the same whether or not you choose to help improve Rehyn.",
      "We may use technical and usage information where necessary to keep the Services reliable and secure. The Privacy Notice explains this processing.",
    ],
  },
  {
    title: "8. Availability, changes and early release",
    paragraphs: [
      "We do not guarantee that the Services will always be available, uninterrupted or error-free. We may change, update, suspend or withdraw features.",
      "Early-release features may change or be removed. We will give reasonable notice where practical.",
      "We may update these Terms. We will notify you of material changes and ask you to accept them again where required. You may stop using and delete your account if you do not agree.",
    ],
  },
  {
    title: "9. Intellectual property",
    paragraphs: [
      "The Services, software, models, algorithms, datasets, methods, content, designs, text, graphics and branding belong to Rehyn or its licensors.",
      "We give you a personal, limited, non-transferable, non-sublicensable and revocable right to use the Services in accordance with these Terms.",
      "You may provide feedback, which Rehyn may use without restriction. Feedback does not include your health information.",
    ],
  },
  {
    title: "10. Ending your use",
    paragraphs: [
      "You may stop using Rehyn at any time and may delete your account through the app or by contacting info@rehyn.com. The Privacy Notice explains what happens to your information.",
      "We may suspend or end access if you breach these Terms, create a safety or security risk, act fraudulently or unlawfully, or if we must do so for legal reasons.",
      "Terms that are intended to continue after your use ends, including ownership, liability and governing-law provisions, will continue to apply.",
    ],
  },
  {
    title: "11. Your statutory rights",
    paragraphs: [
      "Nothing in these Terms affects your statutory rights. Where the Consumer Rights Act 2015 applies, Rehyn must provide the Services with reasonable care and skill.",
    ],
  },
  {
    title: "12. Our liability",
    paragraphs: [
      "Nothing in these Terms excludes liability for death or personal injury caused by negligence, fraud or fraudulent misrepresentation, or any liability that cannot legally be excluded.",
      "Subject to that, Rehyn is not responsible for losses that were not reasonably foreseeable, loss of profit, revenue, business, opportunity or data, events beyond our reasonable control, or reliance on automated guidance where professional or emergency advice was warranted.",
      "Because the early-release Services are free, our total liability arising from the Services is limited to GBP 100 where the law permits.",
      "You are responsible for using the Services safely and within your abilities.",
    ],
  },
  {
    title: "13. General",
    paragraphs: [
      "These Terms and the Privacy Notice form the agreement between you and Rehyn about the Services. If any part is unenforceable, the rest remains effective. A delay in enforcing a right is not a waiver of it.",
      "Rehyn may assign its rights and obligations where your rights are not reduced. You may not transfer yours without our written agreement. No other person has a right to enforce these Terms.",
    ],
  },
  {
    title: "14. Contact, complaints and governing law",
    paragraphs: [
      "Contact info@rehyn.com with questions or complaints. This address is not monitored for emergencies.",
      "These Terms are governed by the law of England and Wales. The courts of England and Wales have jurisdiction, without affecting any mandatory consumer right to bring a claim where you live.",
    ],
  },
];

export const PRIVACY_INTRO =
  "This Privacy Notice explains what information Rehyn collects, why we use it, how long we keep it, who we share it with, and the choices and rights available to you.";

export const PRIVACY_SECTIONS: LegalSection[] = [
  {
    title: "1. The short version",
    paragraphs: [
      "We collect account information, your rehabilitation profile and answers, movement videos, measurements produced from those videos, activity records, messages and technical information.",
      "We use this information to operate your account, build and adapt your rehabilitation plan, show progress, provide support and keep Rehyn secure.",
      "Raw movement videos are used to produce measurements and are then deleted. We retain the derived movement measurements in line with section 9.",
      "We use health or rehabilitation information to train or improve Rehyn's technology only with separate, explicit consent. You can withdraw that consent in Settings without losing access to the Services.",
      "We do not sell your information or use it for advertising.",
    ],
  },
  {
    title: "2. Who we are",
    paragraphs: [
      "Rehyn Ltd is the controller of your personal information. We are incorporated in England and Wales under company number 17417716. Contact us at info@rehyn.com.",
      "ICO registration number: [to be confirmed].",
    ],
  },
  {
    title: "3. Information we collect",
    paragraphs: [
      "Information you give us includes your name, email address and account details; age range, gender, stroke and rehabilitation profile, affected areas, mobility, medical conditions, goals and care information; movement videos; assessment answers; completed activities; messages; support requests; and feedback.",
      "Information generated through the Services may include joint angles, range, speed, step timing, symmetry, stability and other movement measurements; assessment scores; functional findings; rehabilitation plans; progress summaries; and Alira responses.",
      "We also collect technical information such as device and browser type, app version, IP address, diagnostic events, security logs and permission status where needed to operate and protect the Services.",
      "A family member, carer or clinician may give us information about you when they help you use Rehyn. We show you the sharing choices available before information is shared.",
    ],
  },
  {
    title: "4. How and why we use information",
    paragraphs: [
      "Account and service delivery: we use account information to create and manage your account and deliver the Services. Our legal basis is performance of our contract with you under UK GDPR Article 6(1)(b).",
      "Rehabilitation plan and progress: we use your profile, health information, videos and derived measurements to provide assessments, plans and progress. Our legal bases are performance of our contract under Article 6(1)(b) and your explicit consent for health data under Article 9(2)(a).",
      "Safety and security: we use technical and account information to prevent fraud, investigate incidents and protect users and the Services. Our legal basis is our legitimate interests under Article 6(1)(f).",
      "Improving Rehyn: where you opt in, we use eligible information to train, test and evaluate our technology. Our legal bases are consent under Article 6(1)(a) and explicit consent under Article 9(2)(a).",
      "Legal obligations: we may process information to comply with law, regulation or valid legal requests under Article 6(1)(c) and, where applicable, Article 9(2)(g) or 9(2)(i).",
      "Serious harm: exceptionally, we may use information to protect vital interests under Article 6(1)(d) and Article 9(2)(c). Rehyn is not monitored in real time and is not an emergency service.",
    ],
  },
  {
    title: "5. Improving Rehyn",
    paragraphs: [
      "Because Rehyn is an early-release service, we may ask whether you want to help improve its accuracy and reliability. This choice is optional and off by default.",
      "If you opt in, we may use derived movement measurements, assessment results, activity completion, plan adaptations, symptom information and feedback. We replace direct account identifiers with a code and restrict access. We do not use raw movement videos after their normal deletion unless a separate retention choice is offered and you select it.",
      "You can withdraw through Data and permissions or by emailing info@rehyn.com. Withdrawal stops future use for model improvement. It does not make earlier lawful processing unlawful, and it may not be possible to remove the influence of information already used to train a model.",
      "All normal Rehyn features remain available whether or not you opt in. We will ask again before using information for a materially different purpose.",
    ],
  },
  {
    title: "6. Movement videos",
    paragraphs: [
      "Movement videos are uploaded and processed using encryption. We use them to create movement measurements and then delete the raw videos within [retention period to be confirmed].",
      "If Rehyn later offers an option to keep videos for playback or comparison, we will explain the retention period and ask you separately before doing so.",
      "Only record yourself. If another identifiable person appears, they must know about and agree to the recording.",
    ],
  },
  {
    title: "7. Sharing information",
    paragraphs: [
      "We do not sell your information and do not share it for advertising.",
      "We may share information with authorised Rehyn personnel; service providers that host, process, secure or support the Services; professional advisers; authorities where legally required; a successor if Rehyn is reorganised or sold; and people such as a clinician or carer when you ask us to share it.",
      "Service providers must use information only for the services they provide to Rehyn and must protect it appropriately.",
    ],
  },
  {
    title: "8. Where information is held",
    paragraphs: [
      "Rehyn currently stores and processes information in the United Kingdom. If information is transferred to another country, we will use safeguards required by UK data-protection law, such as an adequacy regulation or approved contractual protections.",
      "If the countries or safeguards materially change, we will update this notice.",
    ],
  },
  {
    title: "9. How long we keep information",
    paragraphs: [
      "We keep account information while your account is active and for [period to be confirmed] afterwards where needed for legal, security or support purposes.",
      "Raw movement videos are kept for [period to be confirmed] after measurements are produced. Derived movement measurements and assessment results are kept for [period to be confirmed] so you can view progress. Security logs and consent records are kept for [period to be confirmed].",
      "Where you consent to model improvement, eligible pseudonymised information may remain in controlled training or evaluation datasets. Section 5 explains what happens when you withdraw.",
      "We delete or anonymise information when it is no longer needed, unless the law requires longer retention.",
    ],
  },
  {
    title: "10. Your rights",
    paragraphs: [
      "Depending on the circumstances, you can ask to access your information, correct it, delete it, restrict its use, object to its use, or receive a portable copy. You can withdraw consent at any time.",
      "Contact info@rehyn.com to exercise a right. We may need to verify your identity. We normally respond within one month and do not usually charge a fee.",
      "You can complain to the Information Commissioner's Office at ico.org.uk or 0303 123 1113. We would appreciate the opportunity to address your concern first.",
    ],
  },
  {
    title: "11. Security",
    paragraphs: [
      "We use measures designed to protect information, including encryption in transit and at rest, access controls, role-based permissions, separation of identifiers where appropriate, logging and staff confidentiality requirements.",
      "No online service can guarantee absolute security. Protect your device and account, and contact info@rehyn.com if you suspect unauthorised access.",
      "If a personal-data breach is likely to risk people's rights, we will notify the ICO within the required period and notify affected people when the risk is high.",
    ],
  },
  {
    title: "12. Children",
    paragraphs: [
      "Rehyn is intended for adults aged 18 or over. If we learn that we collected a child's information, we will take steps to delete it. Contact info@rehyn.com if you believe this has happened.",
    ],
  },
  {
    title: "13. Changes to this notice",
    paragraphs: [
      "We may update this notice as Rehyn changes. We will show the new effective date and notify you of material changes. Where the law requires it, we will ask for consent again. Previous versions are available on request.",
    ],
  },
];
