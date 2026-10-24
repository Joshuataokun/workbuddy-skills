## Description:

Renders HTML, SVGs, and web pages as screenshots, social cards, favicons, and app-icon sets.

This skill is ready for commercial/non-commercial use.

## Publisher:

[rockbenben](https://clawhub.ai/user/rockbenben)

### License/Terms of Use:

MIT-0

## Use Case:

Developers and designers use this skill to turn HTML, SVGs, or trusted URLs into screenshots, social previews, and platform-ready icons.

### Deployment Geography for Use:

Global

## Known Risks and Mitigations:

Risk: Rendered pages can run JavaScript and contact the network, including private or local services accessible from the machine.

Mitigation: Render only HTML and URLs you trust; avoid untrusted pages on machines with access to private or local-only services.

Risk: Running the skill requires installing Node dependencies and Playwright Chromium.

Mitigation: Install it only if you are comfortable adding those dependencies and a local browser.

## Reference(s):

- [html-shot project homepage (listed in skill metadata)](https://github.com/rockbenben/aishort-skills/tree/main/skills/html-shot)
- [html-shot ClawHub release](https://clawhub.ai/rockbenben/skills/html-shot)

## Skill Output:

**Output Type(s):** [Image files, HTML link snippets]

**Output Format:** [PNG, JPEG, WebP, ICO, ICNS, or SVG files; optional HTML link tags]

**Output Parameters:** [1D]

**Other Properties Related to Output:** [Supports sized or transparent renders and web, PWA, and desktop icon presets.]

## Skill Version(s):

1.1.6 (source: ClawHub release, SKILL.md frontmatter, package.json)

## Ethical Considerations:

Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment.
