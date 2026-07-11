# The AI Skill Creator: Encode the Spec Twice

## One System Prompt, One Validator, Zero Agents

The last thing I wrote about in this repo family was the [Prompt Optimizer](https://prompt-optimizer-8-854735162550.me-west1.run.app/), a four-agent pipeline: an analyzer, eight parallel judges, a writer, and a critic with a bounded revision loop. I stand by every one of those agents.

The **AI Skill Creator** is its sibling, and it has none of them. A single Gemini call per chat turn replaces the whole pipeline. The same design principle that gave the Optimizer its agents takes them away here, because the two tools verify different kinds of failure.

The Prompt Optimizer needs agents because prompt quality is fuzzy. "Does this prompt realize technique 04?" is a judgment call, so only an LLM can make it, and you pay for a critic. A Gemini Skill is the opposite: a mechanical spec governs it. Whether a folder name is kebab-case is not a judgment call. Anything a regex can check, a regex *should* check; spending a second LLM call on it is waste.

## The Thesis: Same Spec, Two Encodings

The app is a chat that generates skills in Anthropic's Agent Skills format (a folder with a `SKILL.md` plus optional `scripts/`, `references/`, and `assets/` subdirectories), aimed at Gemini instead of Claude. The format's constraints are mechanical, and the app encodes them **twice**.

**Encoding one lives in the system prompt**, for generation. It tells the model, verbatim: "The folder name must be in kebab-case (no spaces, no capitals, no underscores)"; "The main file must be exactly named SKILL.md (case-sensitive)"; the YAML frontmatter `name` must exactly match the folder name; the `description` must be "Under 1024 characters", must "include WHAT the skill does and specific trigger phrases for WHEN to use it", and must not contain XML tags. The body should "use progressive disclosure (keeping instructions focused and linking to files in references/ for deep details)".

**Encoding two lives in deterministic client-side code**, for verification. After every model response, a validator re-checks the same rules with a regex, a YAML parser, and a length comparison. It spends no tokens, and nothing about it is probabilistic.

Generation is probabilistic, so the spec goes into the prompt, where it shifts the output distribution toward compliance. Verification of mechanical constraints is deterministic, so the spec goes into code, where compliance is a boolean. Each encoding sits where it's strong.

Readers of the Prompt Optimizer article will recognize this as technique 08, *own the output*: capabilities are Swiss cheese, so check the work. Over there, the check needed judgment, so it became a critic agent. Here it doesn't, so it became one small validator function in the client.

## How a Turn Works

```
"I need a skill that reviews Terraform plans"
   │
   ▼
chats.create ──── systemInstruction = the spec (encoding #1)
   │              responseMimeType: "application/json" + responseSchema
   ▼
sendMessage ───── ONE non-streaming Gemini call
   │              (gemini-3.5-flash default, gemini-3.1-pro-preview selectable)
   ▼
JSON.parse ────── the schema already guaranteed the shape
   │
   ▼
validator ─────── spec compliance (encoding #2); warnings go into the chat
   │
   ▼
render ────────── Structure / SKILL.md / Optional Artifacts / Python Test
                  tabs, plus Download ZIP
```

Structured output is enforced at the API level: `responseMimeType: "application/json"` plus a `responseSchema` with six required fields: `skillName`, `folderStructure` (an array of `{path, type}` entries), `skillMdContent`, `optionalArtifacts` (an array of `{filePath, content}`), `samplePromptText`, and `messageToUser`. The UI never parses free text hoping to find a code block; it reads named fields from a shape the API was contractually obliged to return.

That's the first layer of the trust boundary. The schema guarantees *shape*. The validator guarantees *spec compliance*. What's left is the part only an LLM can do: writing instructions worth following, choosing trigger phrases a model will match against, deciding what belongs in the `SKILL.md` body versus a `references/` file. That is the only part the app trusts the LLM with.

## The Validator: The Spec as Code

The checks, with the exact patterns from the deployed bundle. First, the frontmatter must exist:

```ts
const match = skillMdContent.match(/^---\n([\s\S]*?)\n---/);
// miss → "Missing or malformed YAML frontmatter.
//         It must start and end with '---'."
```

The captured block goes through **js-yaml**, and a parse failure is its own warning: the model can produce YAML-shaped text that isn't YAML, and a parser is the only honest judge of that. Then the field rules:

- `name` must be present, must equal the `skillName` the model itself declared, and must match

  ```ts
  /^[a-z0-9]+(?:-[a-z0-9]+)*$/
  ```

- `description` must be present, its `length` must stay under 1024 characters, and it must survive

  ```ts
  /<|>/.test(description)   // no XML tags in frontmatter
  ```

Each of these could have been a second LLM call ("review this SKILL.md for spec compliance") at the price of a network round trip, tokens, and a nonzero chance of being wrong about a string length. `.test()` costs microseconds and is never wrong about the thing it checks. The critic-agent pattern earns its keep when the check itself requires judgment; "is this under 1024 characters" requires subtraction.

## The Loop Has a Human in It

When a check fails, the warnings render inline in the chat, under the model's own message, with a hint: *"You can ask me to fix these issues!"*

Nothing repairs itself. That's a design choice, and the second place this app diverges from its sibling. The Prompt Optimizer auto-revises: the critic writes rewrite instructions, the writer redrafts, bounded, no human involved. That's right for it, because its failure reports are themselves LLM judgments that a user can't re-derive at a glance. Here the failure report is an exact, human-readable sentence (`Frontmatter 'name' ("My_Skill") is not valid kebab-case.`), and the repair is a one-line chat message from a person already sitting in a chat.

The tradeoff: this is cheaper (no extra calls, ever) and more transparent (you see which rule failed, in the transcript, forever), but it requires the user to care. If you ignore the yellow box and download the ZIP anyway, the noncompliance ships with you. An unattended, server-side version of this app should close the loop on its own. A chat app with a human watching shouldn't spend their money on invisible repairs.

## The Skill Ships With Its Own Test

My favorite detail is the **Python Test** tab. Alongside the skill, the app emits `test_skill.py`, included in the downloaded ZIP: a runnable harness that loads the generated skill as a system instruction and fires a realistic prompt at it:

```python
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
    config=types.GenerateContentConfig(
        system_instruction=skill_instructions,
        temperature=0.2,
    ),
)
```

The `prompt` is the `samplePromptText`, a required schema field described to the model as "a realistic example of the text or data a user would provide when prompting this skill". The schema forces the model to invent its own test input, so the artifact leaves the app carrying a verification rig: *own the output*, passed down one generation.

## Try It

**[https://skill.genaitools.cloud/](https://skill.genaitools.cloud/)**

Describe a use case, watch the four tabs fill in, and try to provoke the validator: ask for a skill name with underscores, or sneak an `<example>` tag into the description, and see the warnings land in the chat.

## Under the Hood

- **React + Vite SPA**, built as a Google AI Studio Build app; the Gemini calls run in the browser via the **`@google/genai`** SDK (`chats.create` → `sendMessage`, non-streaming). Switching models mid-conversation drops the chat session; the next message creates a fresh chat seeded with the current skill, serialized as a synthetic user/model turn pair. The skill state survives the swap, though the earlier transcript doesn't.
- **js-yaml** parses the frontmatter; **JSZip** assembles the Download ZIP, test harness included.
- **Firebase auth + Firestore** persist your skills: a `skills` collection queried by `uid`, ordered by `createdAt`, with a live snapshot listener feeding the saved-skills list.

One LLM call per turn is the entire inference architecture. Everything else is ordinary, testable, deterministic code.

## Conclusion: Match the Verifier to the Failure Mode

The Prompt Optimizer and the Skill Creator disagree about architecture because their outputs fail in different ways. A prompt fails in fuzzy ways ("technique not realized"), so its checker must be an LLM, and the price is a critic agent and a revision loop. A skill fails mechanically (wrong casing, missing frontmatter, an oversized description), so its checker should be a regex, and the price is nothing.

Spend an LLM where the check needs judgment and a regex where it doesn't. Write the spec twice: once where generation can see it, once where verification can enforce it.

---

*Disclaimer: This code is provided "as-is" as a demonstration only to illustrate a potential solution. The code does not constitute a Google product or service of any kind, and Google offers no support, warranties, or liability of any kind with its regard. Whoever chooses to use this code accepts all responsibility related to it, including for its implementation, use, and ongoing maintenance. For the avoidance of doubt, this code is not eligible for the Google Open Source Software Vulnerability Rewards Program.*
