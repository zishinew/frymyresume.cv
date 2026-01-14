# Installing Monaco Editor

To enable full syntax highlighting and LeetCode-style code editor, install Monaco Editor:

```bash
cd /Users/zishine/VSCODE/Python/resume_critique/frontend
npm install @monaco-editor/react
```

After installing, uncomment the Monaco Editor code in `src/components/TechnicalInterview.tsx`:

1. Uncomment line 2: `import Editor from '@monaco-editor/react'`
2. Uncomment the `<Editor>` component (around line 250)
3. Comment out or remove the fallback `<textarea>` component

The app will work with the textarea fallback, but Monaco Editor provides:
- Full syntax highlighting
- Code autocomplete
- Better code editing experience
- LeetCode-style appearance
