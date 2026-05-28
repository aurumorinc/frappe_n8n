<!-- 
PR Title MUST follow the Conventional Commits standard:
<type>[optional scope]: <description>
Example: feat(auth): add google oauth2 login
-->

## 📝 Description
<!-- 
Provide a longer description to act as the commit body. 
Explain the WHAT and WHY of this change, providing additional contextual information. 
-->


## 🏷️ Type of Change
<!-- 
Check the box that applies to this PR. 
Keep in mind: If your PR conforms to more than one type, you should use GitButler to split it into multiple virtual branches/PRs! 
-->
- [ ] **feat:** A new feature (Correlates with MINOR version bump)
- [ ] **fix:** A bug fix (Correlates with PATCH version bump)
- [ ] **refactor:** A code change that neither fixes a bug nor adds a feature
- [ ] **perf:** A code change that improves performance
- [ ] **docs:** Documentation only changes
- [ ] **style:** Changes that do not affect the meaning of the code (white-space, formatting, etc)
- [ ] **test:** Adding missing tests or correcting existing tests
- [ ] **chore:** Changes to the build process, CI/CD, or auxiliary tools
- [ ] **revert:** Reverts a previous commit

## 💥 Breaking Changes
<!-- 
Does this PR introduce a breaking API/code change? (Correlates with MAJOR version bump). 
-->
- [ ] **No**
- [ ] **Yes** (If yes, your PR title MUST include a `!` before the colon, e.g., `feat(api)!: drop node 6 support`. Please describe the migration path below.)

> *Migration instructions for Breaking Change (if applicable):*


## 🔗 Related Tickets & References
<!-- 
Follow the git trailer format for footers. 
Example: 
Closes #123
Refs: #456 
-->


## ✅ Developer Checklist
- [ ] I have read the PR title to ensure it strictly follows `<type>[optional scope]: <description>`.
- [ ] This PR contains a **single responsibility** (I have not mixed `feat` and `refactor` in the same PR).
- [ ] I have added/updated tests to cover my changes (if applicable).
- [ ] I have updated the documentation accordingly (if applicable).
