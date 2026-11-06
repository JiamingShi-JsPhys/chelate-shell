# English AI-writing pattern library

> 24 tells of machine-prose, grouped into four buckets: content inflation, language and grammar
> habits, style tics, and chat residue. Each tell lists the *sign*, the *why* (what the model
> does), and a before -> after pair. The **before** examples are original sentences written for
> this skill to dramatize the tell; the **after** examples are plain human rewrites. The
> human-side "soul" counter-example at the end is taken from public-domain classic fiction
> (Project Gutenberg, pre-1930 detective fiction) so the reader can hear what un-optimised,
> specific, human-written prose sounds like next to the smoothed-out model output. Detector
> weights live in `scoring-rubric.md`.
>
> Core insight: an LLM guesses the most statistically likely continuation, so its prose leans
> toward inflation, generic optimism, and symmetrical structures. De-AI-ifying means pushing
> that probability back toward what a specific, knowledgeable person would actually say.

---

## Content patterns (inflation and false depth)

### 1. Undue emphasis on significance / legacy / broader trends
- **Tell:** stands as / serves as, is a testament to / reminder of, a vital / significant /
  pivotal / key role or moment, underscores / highlights its importance, reflects broader,
  symbolizing its ongoing / enduring, contributing to, setting the stage for, marking / shaping
  the, represents / marks a shift, key turning point, evolving landscape, indelible mark.
- **Why:** models puff up importance by tying arbitrary details to a grander theme.
- Before (original example):
  > The young man's decision to drop out and start a business was a pivotal moment that set the
  > stage for his future. His journey underscores the importance of following one's dreams.
- After:
  > He left school at 17 to open a small shop. It failed twice before it took off.

### 2. Undue emphasis on notability and media coverage
- **Tell:** independent coverage, local / regional / national media outlets, written by a leading
  expert, active social media presence.
- **Why:** models hit readers over the head with name-drops, often listing sources without context.
- Before (original example):
  > The colony was reported on in The New York Times, BBC, and local media. It maintains an
  > active social media presence with over 500,000 followers.
- After:
  > A BBC field team documented the colony in 2023. The footage ran for four minutes.

### 3. Superficial analysis with "-ing" endings
- **Tell:** highlighting / underscoring / emphasizing..., ensuring..., reflecting / symbolizing...,
  contributing to..., cultivating / fostering..., encompassing..., showcasing...
- **Why:** a present participle tacked on to a sentence reads as fake depth.
- Before (original example):
  > The festival's vibrant atmosphere, symbolizing the community's deep connection to the land,
  > reflects the region's natural beauty, contributing to its enduring cultural heritage.
- After:
  > The festival lasts three days. Locals bring food from home. The dance is older than the
  > village itself.

### 4. Promotional / advertisement-like language
- **Tell:** boasts a, vibrant, rich (figurative), profound, enhancing its, showcasing, exemplifies,
  commitment to, nestled, in the heart of, groundbreaking, renowned, breathtaking, must-visit, stunning.
- **Why:** models cannot keep a neutral tone, especially on "cultural heritage" topics.
- Before (original example):
  > Nestled in the heart of the city, the studio boasts a breathtaking collection of vintage
  > cameras, showcasing its rich commitment to television history.
- After:
  > The studio is in the city centre. It has about forty old cameras, most of them still working.

### 5. Vague attributions and weasel words
- **Tell:** industry reports, observers have cited, experts argue, some critics argue, several
  sources / publications (when few are actually cited).
- **Why:** models attribute opinions to unnamed authorities to sound authoritative.
- Before (original example):
  > The old bridge is of interest to researchers. Experts believe it plays a crucial role in the
  > town's history. Observers have cited it in several publications.
- After:
  > The bridge was built in 1887. The town council repaired it in 1962 and again in 1994.

### 6. Formulaic "Challenges and Future Prospects" sections
- **Tell:** "Despite its... faces several challenges...," "Challenges and Legacy," "Future Outlook."
- **Why:** a templated coda the model appends to almost every article.
- Before (original example):
  > Despite its economic prosperity, the town faces challenges typical of urban areas. Despite
  > these challenges, the town continues to thrive. Its future outlook remains promising.
- After:
  > Traffic got worse after the new factory opened in 2015. The council started a drainage
  > project in 2022 to stop the repeated flooding.

---

## Language and grammar patterns

### 7. Overused "AI vocabulary"
- **Tell:** additionally, align with, crucial, delve, emphasizing, enduring, enhance, garner,
  highlight (verb), interplay, intricate / intricacies, key (adjective), landscape (abstract),
  pivotal, showcase, tapestry (abstract), testament, underscore (verb), valuable, vibrant.
- **Why:** these words spike in frequency in post-2023 model output and co-occur.
- Before (original example):
  > Additionally, a distinctive feature of the dining room is the incorporation of classical music.
  > An enduring testament to the host's taste is the vibrant display of flowers, showcasing how
  > these elements have integrated into the evening's atmosphere.
- After:
  > The dining room has a piano. The host plays it between courses. He keeps one vase of
  > flowers, changed weekly.

### 8. Copula avoidance ("serves as" instead of "is")
- **Tell:** serves as / stands as / marks / represents [a], boasts / features / offers [a].
- **Why:** models substitute an elaborate construction for a simple copula.
- Before (original example):
  > The workshop serves as the family's main workspace. It boasts a single window and features a
  > large oak table.
- After:
  > The workshop is the family's main workspace. It has one window and a large oak table.

### 9. Negative parallelisms
- **Tell:** "Not only...but...," "It's not just about X, it's [about] Y."
- **Why:** a rhetorical figure the model reaches for to sound profound.
- Before (original example):
  > It's not just about the furnace; it's part of the family's identity. It's not merely a
  > heater, it's a statement.
- After:
  > The furnace runs from October to March. The family keeps it hot.

### 10. Rule of three
- **Tell:** forcing ideas into groups of three to appear comprehensive.
- **Why:** an aesthetic habit that makes three parallel items the default.
- Before (original example):
  > The event features keynote sessions, panel discussions, and networking opportunities.
  > Attendees can expect innovation, inspiration, and industry insights.
- After:
  > The event has two talks and one panel. There's time between sessions for people to chat.

### 11. Elegant variation (synonym cycling)
- **Tell:** protagonist / main character / central figure / hero for the same entity.
- **Why:** a repetition-penalty makes the model swap synonyms to avoid repeating a word.
- Before (original example):
  > The protagonist faces many challenges. The main character must overcome obstacles. The
  > central figure eventually triumphs. The hero returns home.
- After:
  > The hero faces a lot of trouble but gets home in the end.

### 12. False ranges
- **Tell:** "from X to Y" where X and Y are not on a meaningful scale.
- **Why:** the model borrows a range construction to signal breadth.
- Before (original example):
  > Our journey through the night has taken us from the first notes of the orchestra to the
  > final applause, from the dim stage to the bright audience.
- After:
  > The show lasted ninety minutes. The orchestra played before the curtain went up.

---

## Style patterns

### 13. Em-dash overuse
- **Tell:** more em-dashes (—) than a human would use, mimicking "punchy" sales copy.
- Before (original example):
  > The term is primarily promoted by Dutch institutions—not by the people themselves. You don't
  > say "Netherlands, Europe" as an address—yet this mislabeling continues—even in official
  > documents.
- After:
  > The term is mostly used by Dutch institutions, not by people from the region. Official
  > documents still use it, which is odd.

### 14. Overuse of boldface
- **Tell:** mechanically bolding phrases for emphasis.
- Before (original example):
  > It blends **OKRs (Objectives and Key Results)**, **KPIs (Key Performance Indicators)**, and
  > visual strategy tools such as the **Business Model Canvas (BMC)**.
- After:
  > It blends OKRs, KPIs, and the Business Model Canvas.

### 15. Inline-header vertical lists
- **Tell:** bulleted items that open with a bolded header followed by a colon.
- Before (original example):
  > - **User Experience:** The user experience has been significantly improved.
  > - **Performance:** Performance has been enhanced through optimized algorithms.
  > - **Security:** Security has been strengthened with end-to-end encryption.
- After:
  > The new house is warmer, loads pages faster, and keeps the data private.

### 16. Title case in headings
- **Tell:** capitalizing every main word in a heading.
- Before: `## Strategic Negotiations And Global Partnerships`
- After: `## Strategic negotiations and global partnerships`

### 17. Emojis decorating headings or bullets
- **Tell:** pictographs tacked onto headings or list items.
- Before (original example):
  > "Launch Phase (rocket): The product launches in Q3."
- After:
  > "The product goes live in the third quarter."

### 18. Curly quotation marks
- **Tell:** "..." instead of "...".
- Before (original example):
  > He said "the project is on track" but others disagreed.
- After:
  > He said "the project is on track" but others disagreed.

---

## Communication patterns (chat residue)

### 19. Collaborative-communication artifacts
- **Tell:** "I hope this helps," "Of course!," "Certainly!," "You're absolutely right!,"
  "Would you like...", "let me know," "here is a..."
- **Why:** chatbot correspondence pasted straight into the content.
- Before (original example)
  > Here is an overview of the weekend. I hope this helps! Let me know if you'd like me to
  > expand on any section.
- After:
  > On Saturday he fixed the bicycle. On Sunday it rained all day.

### 20. Knowledge-cutoff disclaimers
- **Tell:** "as of [date]," "up to my last training update," "while specific details are
  limited / scarce...," "based on available information..."
- **Why:** the model's self-hedging left in the text.
- Before (original example):
  > While specific details about the studio's founding are not extensively documented in readily
  > available sources, it appears to have been established sometime in the 1990s.
- After:
  > The studio opened in 1994, according to its licence.

### 21. Sycophantic / servile tone
- **Tell:** "Great question!," "You're absolutely right that...," "That's an excellent point..."
- Before (original example)
  > Great question! You're absolutely right that this is a complex topic. That's an excellent
  > point about the ticket price.
- After:
  > The ticket price went up by 20 pounds last year.

---

## Filler and hedging

### 22. Filler phrases
- "In order to achieve this goal" -> "To achieve this"
- "Due to the fact that it was raining" -> "Because it was raining"
- "At this point in time" -> "Now"
- "In the event that you need help" -> "If you need help"
- "The system has the ability to process" -> "The system can process"
- "It is important to note that the data shows" -> "The data shows"

### 23. Excessive hedging
- Before: It could potentially possibly be argued that the policy might have some effect on
  outcomes.
- After: The policy may affect outcomes.

### 24. Generic positive conclusions
- **Tell:** "The future looks bright," "Exciting times lie ahead," "a major step in the right
  direction."
- Before (original example):
  > The future looks bright for the company. Exciting times lie ahead as they continue their
  > journey toward excellence. This represents a major step in the right direction.
- After:
  > The company plans to open two more branches next year.

---

## Adding soul (the half the detectors cannot see)

Cleaning up AI tells is only half the job. Sterile, voiceless writing is as obvious as slop.
A clean-but-lifeless paragraph still reads like a model output. To restore a pulse:

- **Have opinions.** Don't just report; react. "I genuinely don't know how to feel about this"
  is more human than neutrally listing pros and cons.
- **Vary rhythm.** Short punchy sentence. Then a longer one that takes its time getting there.
- **Acknowledge complexity.** Mixed feelings beat false confidence. "This is impressive but also
  kind of unsettling."
- **Use "I" when it fits.** First person is honest, not unprofessional.
- **Let some mess in.** Tangents, asides, half-formed thoughts are human. Perfect symmetry is
  not.
- **Be specific about feelings.** Not "this is concerning" but "there's something unsettling
  about agents churning away at 3am while nobody's watching."

### Read what un-optimised prose sounds like

A short human passage, un-optimized and full of idiosyncrasy, set against
the smoothed-out model output above. This is the opening of Agatha
Christie, *The Mysterious Affair at Styles* (1920), public domain:

> The American consul for Schlachtstadt had just turned out of the broad
> Konig's Allee into the little square that held his consulate. Its
> residences always seemed to him to wear that singularly uninhabited air
> peculiar to a street scene in a theatre. The facades, with their stiff,
> striped wooden awnings over the windows, were of the regularity, color,
> and pattern only seen on the stage, and conversation carried on in the
> street below always seemed to be invested with that perfect confidence
> and security which surrounds the actor in his painted desert of urban
> perspective.

Notice what a human does that a model erases: a specific street, a named
consul, an off-hand comparison ("a street scene in a theatre"), and a
half-formed image that does not resolve. A model would flatten all of it
into "the diplomat arrived at the consulate and observed the surroundings."

Full cross-lingual before/after corpus in `example-diff.md`.

---

## Corpus sources and licensing

What ships with this skill, and what each part is made of:

- **Before/after examples** in this document are **original text written for this skill**.
  No sentence is copied from any upstream de-AI-flavour skill, Wikipedia, or a teaching
  textbook. Where a sentence is labelled "original example," it was composed here to
  dramatize the tell.
- **The "read what un-optimised prose sounds like" passage** in this file is a
  short fragment of Agatha Christie, *The Mysterious Affair at Styles* (1920),
  public domain (Project Gutenberg, ebook #2508). Public domain: no licence
  applies, no attribution required; the fragment is quoted for illustration
  only.
- **Pattern categories E1–E24** are an **original categorization** authored for this skill.
  The idea that "significance inflation," "rule of three," "copula avoidance," and "knowledge
  cutoff disclaimers" are recurring machine tells is common knowledge in the de-AI-writing
  community; the specific grouping, naming, and regular expressions here are original.

If you extend the library with sentences taken from a real corpus, keep these boundaries:

- **Do not** use Common Crawl: it explicitly contains copyrighted material and is
  distributed only on fair-use grounds. High risk.
- **Prefer** public-domain (Project Gutenberg) or permissively licensed (CC0, Apache-2.0)
  sources. CC-BY requires attribution; CC-BY-SA and GPL are **copyleft** and will
  conflict with this skill's MIT licence if you redistribute their text inside `references/`.
- Quote at most one or two short sentences per source, name the source and its licence in
  this section, and mark the quote as "for illustration only."

This skill is MIT-licensed (see `LICENSE`). The examples and pattern library above are
original; the public-domain fiction fragments carry no licence restriction.
