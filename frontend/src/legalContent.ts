export type LegalSection = {
  title: string;
  paragraphs: string[];
  bullets?: string[];
};

export const LEGAL_VERSION = "1.0";
export const LEGAL_EFFECTIVE_DATE = "To be confirmed";

// The section text below reproduces the approved legal documents verbatim
// (Rehyn App Terms of Use v1.0 and Rehyn App Privacy Notice v1.0).
// Do not edit this wording without legal review. Bracketed values must be
// replaced with the real figures before release.

export const TERMS_INTRO =
  "Please read these Terms of Use before you use Rehyn. They are a legal agreement between you and Rehyn Ltd. Section 2 contains important safety information, and section 7 explains how Rehyn uses information to improve its technology. If you do not accept these Terms, do not use the Services.";

export const TERMS_SECTIONS: LegalSection[] = [
  {
    title: "1. Who we are and what these Terms cover",
    paragraphs: [
      "1.1 Rehyn Ltd, a company incorporated in England and Wales with company number 17417716 and registered office at 64 Woodnesborough Road, Sandwich, Kent CT13 0AD, operates the Rehyn mobile application, website and connected features (together, the \"Services\"). Rehyn is referred to in these Terms as \"Rehyn\", \"we\" or \"us\", and the person using the Services is referred to as \"you\".",
      "1.2 These Terms of Use, together with the Rehyn Privacy Notice, govern your access to and use of the Services. By creating an account or otherwise using the Services, you confirm that you accept these Terms and that you are legally able to do so.",
      "1.3 The Services are currently provided free of charge as an early release. This means some features are still in development, may change or be withdrawn, and may not perform with the accuracy or reliability of a finished product. Section 8 explains what this means for availability, and section 12 explains the limits of our liability.",
      "1.4 The Services are intended for people aged 18 or over. If you are under 18, you may not create an account or use the Services.",
    ],
  },
  {
    title: "2. Important safety information",
    paragraphs: [
      "2.1 Rehyn provides digital rehabilitation support, including movement capture, functional measurements, guided activities, progress tracking and personalised rehabilitation plans. Rehyn does not provide emergency care, does not diagnose any condition, and does not guarantee any particular recovery outcome.",
      "2.2 The Services do not replace assessment, treatment or advice from a doctor, physiotherapist, occupational therapist or other qualified healthcare professional. Where a professional has given you instructions, follow those instructions. If guidance shown in the Services conflicts with advice you have been given by a professional, follow the professional advice and tell us at info@rehyn.com.",
      "2.3 Before you begin using the Services, and before you take on any new or more demanding activity within them, you should confirm with a qualified healthcare professional that the activity is safe and suitable for you.",
      "2.4 Use the Services only in a safe space, with clear floor area, suitable footwear and support or supervision if you need it. Stop any activity immediately, and seek medical advice, if you experience pain, dizziness, breathlessness, chest discomfort, sudden weakness, numbness, confusion, difficulty speaking, loss of balance, a fall or any other symptom that concerns you.",
      "2.5 In an emergency, or if you think you may be having a stroke or another medical emergency, call 999 in the United Kingdom or your local emergency number. Do not use the Services to seek urgent help. Rehyn is not monitored in real time and no one at Rehyn will see an alert and respond to it.",
    ],
  },
  {
    title: "3. Your account",
    paragraphs: [
      "3.1 You must give accurate, current and complete information when you create your account and keep it up to date. You are responsible for the security of your login details and for activity carried out through your account.",
      "3.2 Do not share your account with anyone else and do not use anyone else’s account. If you believe someone has accessed your account without permission, tell us promptly at info@rehyn.com.",
      "3.3 If a family member, carer or supporter helps you use the Services, they must follow these Terms. You remain responsible for what happens through your account, and you should only allow someone to help you if you are content for them to see the information in it.",
    ],
  },
  {
    title: "4. Using Rehyn responsibly",
    paragraphs: [
      "You agree not to:",
    ],
    bullets: [
      "use the Services in an unsafe way, beyond your physical capability, or contrary to advice from a qualified healthcare professional;",
      "record, upload or share content that is unlawful, harmful, abusive, misleading or that infringes anyone else’s rights, including recordings of another person made without that person’s knowledge and agreement;",
      "upload content about another person, or use the Services on another person’s behalf, unless that person understands and agrees;",
      "copy, modify, reverse engineer, decompile, scrape, or attempt to extract the models, algorithms, datasets or source code underlying the Services;",
      "interfere with, overload, probe or attempt to gain unauthorised access to the Services or any system connected to them; or",
      "use the Services for any commercial purpose, or to build or train any competing product or model, without our written permission.",
    ],
  },
  {
    title: "5. Your content and the rights you give us",
    paragraphs: [
      "5.1 You may provide movement videos, assessment answers, rehabilitation goals, activity records, messages and feedback through the Services (\"Your Content\"). You keep ownership of Your Content.",
      "5.2 You grant Rehyn a non exclusive, worldwide, royalty free licence to host, store, process, analyse and display Your Content strictly as needed to operate the Services for you: to derive measurements, generate and adapt your rehabilitation plan, show your progress, provide support, keep the Services secure and meet our legal obligations. This licence lasts as long as we hold Your Content under the Privacy Notice and ends when the content is deleted.",
      "5.3 The licence in clause 5.2 does not by itself permit us to use Your Content to train or develop our models. That is a separate matter, dealt with in section 7, and it happens only where you have given specific consent.",
      "5.4 Movement videos are processed to extract the measurements the relevant assessment needs. Raw video is then deleted in line with the Privacy Notice. Derived measurements and results are kept as described there.",
      "5.5 You confirm that you have the right to provide Your Content, and that anything you upload showing another identifiable person is uploaded with that person’s knowledge and agreement.",
    ],
  },
  {
    title: "6. Automated guidance and Alira",
    paragraphs: [
      "6.1 Rehyn uses automated systems, including its rehabilitation agent Alira, to generate measurements, build and adapt rehabilitation plans, and provide prompts, encouragement and feedback. These outputs are produced automatically from the information available to the system.",
      "6.2 Automated outputs are supportive guidance only. They may be incomplete, inaccurate or unsuitable for your particular circumstances, and they are not a clinical assessment or a professional recommendation. You should apply your own judgement and seek professional advice where you are unsure whether an activity is safe or appropriate for you. You decide whether to follow any guidance the Services show you.",
      "6.3 Alira is a software feature. It is not a clinician, it does not supervise you, and it cannot detect an emergency or summon help.",
      "6.4 The Services do not make decisions that produce legal effects concerning you or similarly significantly affect you within the meaning of data protection law. If that ever changes, we will tell you and explain your rights before it takes effect.",
    ],
  },
  {
    title: "7. Using information to improve Rehyn",
    paragraphs: [
      "7.1 Rehyn is an early release, and part of its purpose is to improve the accuracy of its measurement and rehabilitation technology. We are open about this because the law requires it and because you are entitled to decide.",
      "7.2 Information about your health, rehabilitation and physical function is special category personal data. We will use that information to develop, train, test and evaluate our models and features only where you have given separate, specific and explicit consent through the consent screen in the app or the \"Help improve Rehyn\" setting. That consent is asked for on its own. Accepting these Terms is not consent for this purpose, and we will not treat it as consent.",
      "7.3 You can withdraw that consent at any time in Settings, or by emailing info@rehyn.com. Withdrawal takes effect from the point you make it and stops any further use of your information for improvement purposes. It does not make earlier lawful use unlawful, and it does not affect the processing we must carry out to run your account, deliver your rehabilitation plan, keep the Services secure, meet legal obligations or handle a legal claim.",
      "7.4 Whether or not you give that consent, you keep full access to the Services, your rehabilitation plan and every feature available to you. We do not restrict, downgrade or price the Services differently based on your answer.",
      "7.5 Separately from clause 7.2, we use technical and usage information, such as crash reports, error logs, device type and feature usage, to keep the Services working, secure and stable. The Privacy Notice explains this in full.",
    ],
  },
  {
    title: "8. Availability, changes and early release",
    paragraphs: [
      "8.1 We aim to keep the Services available and working well, but we do not guarantee uninterrupted or error free access. We may change, update, suspend or withdraw all or part of the Services, including for security, maintenance, legal compliance, regulatory reasons or product development.",
      "8.2 Because the Services are provided free of charge as an early release, features may change significantly or be removed. Where a change materially affects how you use the Services, we will give you reasonable notice where it is practical to do so.",
      "8.3 We may update these Terms. Where a change is material we will give reasonable notice through the app, by email or by another appropriate method before it takes effect. If you continue to use the Services after that date, the updated Terms apply to you. If you do not accept them, you may stop using the Services and ask us to delete your account.",
    ],
  },
  {
    title: "9. Intellectual property",
    paragraphs: [
      "9.1 The Services, including their software, models, algorithms, datasets, assessment methods, exercise content, design, text, graphics and branding, belong to Rehyn or its licensors and are protected by intellectual property law. Nothing in these Terms transfers any of those rights to you.",
      "9.2 We grant you a personal, limited, non transferable, non sublicensable and revocable right to use the Services for your own rehabilitation, in accordance with these Terms. No other rights are granted, by implication or otherwise.",
      "9.3 If you send us feedback, suggestions or ideas about the Services, we may use them without restriction and without any obligation to you. This clause does not apply to your health information, which is dealt with in section 7 and in the Privacy Notice.",
    ],
  },
  {
    title: "10. Ending your use of Rehyn",
    paragraphs: [
      "10.1 You may stop using the Services at any time, and you may ask us to close and delete your account through the app or by emailing info@rehyn.com. The Privacy Notice explains what happens to your information when you do.",
      "10.2 We may suspend or end your access where it is reasonably necessary, including where you have breached these Terms, where there is a safety concern, suspected fraud or unlawful activity, a risk to the Services or other users, or a legal or regulatory requirement. Where it is reasonable and lawful to do so, we will tell you why.",
      "10.3 Sections 5.5, 9, 11, 12 and 13, and any other provision intended to survive, continue to apply after your use of the Services ends.",
    ],
  },
  {
    title: "11. Your statutory rights",
    paragraphs: [
      "11.1 The Services are supplied free of charge. Nothing in these Terms affects your rights under the Consumer Rights Act 2015 or any other law that applies to you and cannot be excluded by agreement. Where the law requires us to provide a digital service with reasonable care and skill, we will do so.",
    ],
  },
  {
    title: "12. Our liability to you",
    paragraphs: [
      "12.1 Nothing in these Terms excludes or limits our liability for death or personal injury caused by our negligence, for fraud or fraudulent misrepresentation, or for any other liability that cannot lawfully be excluded or limited.",
      "12.2 Subject to clause 12.1, and to the fullest extent permitted by law, we are not liable for: loss that was not reasonably foreseeable when you started using the Services; loss of profit, revenue, business or opportunity; loss or corruption of data beyond our reasonable control; or loss arising because you relied on automated guidance in circumstances where a reasonable person would have sought professional or emergency assistance.",
      "12.3 Subject to clause 12.1, and because the Services are supplied free of charge, our total liability to you in connection with the Services is limited to £100.",
      "12.4 You are responsible for using the Services safely, for following clause 2, and for the decisions you make about your own rehabilitation.",
    ],
  },
  {
    title: "13. General",
    paragraphs: [
      "13.1 These Terms and the Privacy Notice are the entire agreement between you and Rehyn about the Services.",
      "13.2 If any provision is found to be invalid or unenforceable, the rest continues in force.",
      "13.3 If we do not immediately enforce a right, that does not mean we have given it up.",
      "13.4 You may not transfer your rights under these Terms. We may transfer ours to a successor to our business, and we will tell you if we do.",
      "13.5 A person who is not a party to these Terms has no right under the Contracts (Rights of Third Parties) Act 1999 to enforce any of them.",
    ],
  },
  {
    title: "14. Contact, complaints and governing law",
    paragraphs: [
      "14.1 For questions, complaints, safety concerns or support, contact info@rehyn.com. We aim to acknowledge safety related messages promptly, but the Services are not monitored in real time and you must not rely on them for urgent help.",
      "14.2 These Terms and any dispute or claim arising out of or in connection with them, including non contractual disputes, are governed by the law of England and Wales.",
      "14.3 The courts of England and Wales have exclusive jurisdiction, except that if you live elsewhere in the United Kingdom or in another country, you may bring proceedings in your own courts where the law of that place gives you that right as a consumer.",
    ],
  },
];

export const PRIVACY_INTRO =
  "This notice explains what personal information Rehyn collects, why we use it, how long we keep it, who we share it with and what rights you have. Rehyn Ltd is the controller of that information. Section 5 explains how we use information to improve our technology, and how you control that.";

export const PRIVACY_SECTIONS: LegalSection[] = [
  {
    title: "1. The short version",
    paragraphs: [
      "What we collect. We collect account details, information about your rehabilitation, movement videos you record, the measurements taken from those videos, and technical information about the app.",
      "Why we use it. To run your account, produce and adapt your rehabilitation plan, show your progress, support you and keep the Services secure.",
      "Movement videos. We use raw video to take the measurements the assessment needs, then delete the raw video. We keep the measurements.",
      "Training our models. We use your health and rehabilitation information to train and improve our models only if you give separate, explicit consent, and you can withdraw it at any time in Settings without losing any part of the Services.",
      "Selling. We do not sell your personal information, and we do not use it for advertising.",
    ],
  },
  {
    title: "2. Who we are",
    paragraphs: [
      "2.1 Rehyn Ltd, company number 17417716, registered in the United Kingdom, is the controller of the personal information described in this notice. We are registered with the Information Commissioner’s Office under registration number [ICO registration number].",
      "2.2 For any privacy question, or to exercise your rights, contact info@rehyn.com.",
    ],
  },
  {
    title: "3. The information we collect",
    paragraphs: [
      "Information you give us",
      "Account information: name, email address, login credentials and account settings.",
      "Rehabilitation profile: information you choose to give about your stroke or condition, the date of your stroke, affected side, mobility, rehabilitation goals, current capability, and any notes you add. This is information about your health.",
      "Movement videos: videos you record or upload of yourself performing standardised assessment tasks, such as reach, grasp, hand function, gait, sit to stand, balance and turning tasks. These videos show you and are information about your health.",
      "Assessment and activity information: answers to assessment questions, reported symptoms, pain or difficulty ratings, activity completion and any feedback you give on how an activity went.",
      "Communications: messages, questions, support requests and survey responses you send us.",
      "Information the Services generate",
      "Derived measurements and records: measurements derived from your videos, such as joint angles, range of movement, speed, step length, symmetry, stability and other functional scores; your rehabilitation plan and how it adapts; progress trends over time; and prompts and interactions with Alira.",
      "Technical information: app version, device model, operating system, language, time zone, IP address, crash reports, error logs, performance data and security event records.",
      "Information from other people",
      "If a family member, carer or clinician helps you use the Services, information may reach us through them. If you ever choose to share your progress with a clinician or service, we will tell you clearly what will be shared before it happens.",
    ],
  },
  {
    title: "4. How and why we use your information",
    paragraphs: [
      "The table below is set out purpose by purpose. Where the information concerns your health, we identify both the lawful basis under Article 6 UK GDPR and the additional condition under Article 9 UK GDPR that applies to health information.",
      "a) Creating and running your account",
      "What we do: Register you, authenticate you, maintain your settings and provide customer support.",
      "Lawful basis: Article 6(1)(b), performance of a contract with you (these Terms of Use).",
      "b) Delivering your rehabilitation plan",
      "What we do: Process your movement videos and assessment answers to produce measurements, generate and adapt your personalised plan, deliver guided activities and show your progress.",
      "Lawful basis: Article 6(1)(b), performance of a contract with you.",
      "Health information condition: Article 9(2)(a), your explicit consent, given when you first set up your rehabilitation profile. Without it we cannot provide a rehabilitation plan, because the plan is built from health information. [Confirm with your solicitor whether Article 9(2)(h) applies to any part of this processing once clinical partners are involved.]",
      "c) Keeping the Services safe, secure and working",
      "What we do: Diagnose faults, prevent and investigate misuse or fraud, maintain security, and monitor performance and stability.",
      "Lawful basis: Article 6(1)(f), our legitimate interests in operating a secure and reliable service. We have assessed that this does not override your rights, because the information used is technical rather than clinical wherever that is possible.",
      "d) Improving accuracy and training our models",
      "What we do: Use rehabilitation and movement information to develop, train, test, validate and improve the accuracy of our measurement models, Alira and other features, and to build the evidence base for our technology.",
      "Lawful basis: Article 6(1)(a), your consent.",
      "Health information condition: Article 9(2)(a), your explicit, separate consent. [Where processing is carried out as scientific research, confirm with your solicitor whether Article 9(2)(j) and the safeguards in Schedule 1 Part 1 paragraph 4 of the Data Protection Act 2018 are the appropriate route, and update this section accordingly.]",
      "Your control: This purpose is optional. See section 5.",
      "e) Meeting legal and regulatory obligations",
      "What we do: Keep records we are required to keep, respond to lawful requests, and meet obligations relating to safety, product regulation and data protection.",
      "Lawful basis: Article 6(1)(c), legal obligation. For health information, Article 9(2)(g) or 9(2)(i) as applicable, including reasons of public interest in the area of public health and product safety.",
      "f) Protecting people from serious harm",
      "What we do: Act where we reasonably believe there is a risk to someone’s life or safety.",
      "Lawful basis: Article 6(1)(d), vital interests, and Article 9(2)(c) for health information. This is exceptional. Rehyn is not monitored in real time and you must never rely on it for urgent help.",
    ],
  },
  {
    title: "5. Improving Rehyn, and your control over it",
    paragraphs: [
      "5.1 Rehyn is an early release. Part of why it exists at this stage is to improve the accuracy of the technology, and that improvement depends on real rehabilitation data. We would rather say this plainly than bury it.",
      "5.2 We will use your rehabilitation and movement information for that purpose only if you give explicit consent. We ask for that consent separately, on its own screen, in clear terms, and it is switched off unless you switch it on. Accepting the Terms of Use is not consent for this purpose and we will not treat it as consent.",
      "5.3 If you consent, the information used may include derived movement measurements, assessment outcomes, activity completion, plan adaptations, reported symptoms and feedback. We do not use raw movement video for this purpose after the measurements have been taken and the raw video has been deleted, unless you have given separate consent for video retention through the option described in clause 6.3.",
      "5.4 Before information is used for this purpose we remove direct identifiers such as your name, email address and account identifiers, and replace them with a pseudonym so that the working dataset is not directly identifying. Access is restricted to the people who need it. We do not attempt to re identify anyone in that dataset.",
      "5.5 You can withdraw consent at any time in Settings under \"Help improve Rehyn\", or by emailing info@rehyn.com. Withdrawal is as easy as giving consent. It takes effect from the moment you make it and stops further use of your information for this purpose. It does not make earlier use unlawful, and it does not affect processing under the other purposes in section 4.",
      "5.6 Where a model has already been trained, withdrawing consent stops your information being used in future training and removes it from our training datasets. It may not be possible to remove the influence of information already incorporated into a model that has been trained and released. We say this plainly because it affects your decision.",
      "5.7 Your access to the Services does not depend on your answer. Every feature, and your full rehabilitation plan, remain available to you either way.",
      "5.8 If we ever want to use your information for a materially different purpose, such as sharing a dataset with a research partner or a commercial third party, we will ask you again first.",
    ],
  },
  {
    title: "6. Movement videos",
    paragraphs: [
      "6.1 Movement videos are the most sensitive information the Services handle, so we treat them separately. A video is uploaded over an encrypted connection, processed to extract the measurements the assessment requires, and the raw video is then deleted.",
      "6.2 Raw video is deleted within [insert number] days of the measurements being taken, and sooner where processing completes earlier. [Confirm the operational retention period before publication and keep this figure accurate.]",
      "6.3 If we offer you the option to keep a video for longer, for example so you can compare your movement over time, or so it can be used to improve our models, we will ask for that separately and explain exactly what it means. It is optional and you can change your mind.",
      "6.4 Record only yourself. If another person appears in a video, you must have their knowledge and agreement.",
    ],
  },
  {
    title: "7. Who we share information with",
    paragraphs: [
      "We do not sell your personal information and we do not share it for advertising. We share it only in these situations:",
      "Rehyn personnel who need access to operate, support or secure the Services, under confidentiality obligations and access controls.",
      "Service providers who process information on our behalf under a written contract that meets Article 28 UK GDPR, for example cloud hosting, storage, error reporting and communications. A current list is available on request from info@rehyn.com. [Maintain that list and keep the contracts in place before launch.]",
      "Professional advisers such as lawyers, accountants, auditors and insurers, where they need it and under a duty of confidence.",
      "Regulators, law enforcement, courts or other authorities where we are required or permitted by law to disclose, including reporting obligations relating to safety.",
      "A buyer or successor, in connection with a reorganisation, investment, merger or sale of our business or assets, subject to appropriate protections and to this notice continuing to apply.",
      "Anyone else, where you ask us to or agree to it, such as a clinician you choose to share your progress with.",
    ],
  },
  {
    title: "8. Where your information is held",
    paragraphs: [
      "8.1 Your information is stored and processed in the United Kingdom [and the European Economic Area, if applicable. Confirm and keep accurate].",
      "8.2 If we ever transfer personal information outside the United Kingdom, we will only do so where the law allows and with appropriate safeguards in place, such as UK adequacy regulations or the International Data Transfer Agreement or Addendum, together with a transfer risk assessment. You can ask us for details.",
      "8.3 Where the Services are made available in another country, we will comply with the data protection law of that country and update this notice accordingly.",
    ],
  },
  {
    title: "9. How long we keep information",
    paragraphs: [
      "Account information: for as long as your account is open, and for [insert period, for example 12 months] after you close it, unless we must keep it longer.",
      "Raw movement videos: deleted after measurements are taken, within [insert number] days, unless you have chosen retention under clause 6.3.",
      "Derived measurements, assessments and plans: kept while your account is open so your rehabilitation record stays intact, and for [insert period] afterwards.",
      "Technical and security logs: kept for [insert period] for security and diagnostic purposes.",
      "Consent records: kept for as long as the record of consent must be evidenced, and for [insert period] afterwards, so we can show what you agreed to and when.",
      "Training datasets: information already incorporated into a pseudonymised training dataset is retained under that pseudonym, and is removed from future training when you withdraw consent, as described in clause 5.6.",
      "When a retention period ends we delete the information or irreversibly anonymise it so that it is no longer personal information. [Set each period before publication and record the reasoning.]",
    ],
  },
  {
    title: "10. Your rights",
    paragraphs: [
      "Under UK data protection law you have the right to:",
      "ask for a copy of the personal information we hold about you;",
      "ask us to correct information that is inaccurate or incomplete;",
      "ask us to delete your information, in the circumstances where that right applies;",
      "ask us to restrict how we use your information;",
      "object to processing based on our legitimate interests;",
      "ask for a portable copy of information you gave us, in a machine readable format; and",
      "withdraw consent at any time, where we rely on consent, without affecting the lawfulness of use before you withdrew it.",
      "10.1 To exercise any right, email info@rehyn.com. We will respond within one month, and will tell you if we need longer because the request is complex. We may need to verify your identity first. Exercising your rights is free unless a request is manifestly unfounded or excessive.",
      "10.2 If you are unhappy with how we have handled your information, please tell us first so we can put it right. You also have the right to complain to the Information Commissioner’s Office at ico.org.uk, or by calling 0303 123 1113.",
    ],
  },
  {
    title: "11. Security",
    paragraphs: [
      "11.1 We use technical and organisational measures designed to protect your information, including encryption in transit and at rest, access controls and role based permissions, separation of identifying information from working datasets, logging and monitoring, and staff confidentiality obligations. [Keep this description accurate as the technical setup develops. Do not claim a control that is not in place.]",
      "11.2 No online service can be completely secure. Please protect your device and your login details and tell us at info@rehyn.com if you think your account has been accessed without permission.",
      "11.3 If a personal data breach occurs that is likely to result in a risk to your rights and freedoms, we will report it to the Information Commissioner’s Office within 72 hours of becoming aware of it, and we will tell you directly where the risk to you is high.",
    ],
  },
  {
    title: "12. Children",
    paragraphs: [
      "12.1 The Services are for people aged 18 or over. We do not knowingly collect information from anyone under 18. If we learn that we have, we will delete it. If you believe a person under 18 has given us information, contact info@rehyn.com.",
    ],
  },
  {
    title: "13. Changes to this notice",
    paragraphs: [
      "13.1 We may update this notice as the Services develop or the law changes. The effective date at the top shows the current version, and we keep previous versions available on request.",
      "13.2 Where a change is significant, we will tell you through the app, by email or by another appropriate method before it takes effect. If a change means we want to use your information for a new purpose that relies on consent, we will ask you again rather than assume.",
    ],
  },
];
