# Frontend Debugging Guide

If nothing is showing on the frontend, check the following:

## 1. Check if the dev server is running
```bash
cd frontend
npm run dev
```

You should see:
```
  VITE v7.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

## 2. Check browser console for errors
Open browser DevTools (F12) and check the Console tab for any errors.

Common issues:
- Module not found errors
- Import errors
- TypeScript errors

## 3. Verify all files exist
Make sure these files exist:
- `/frontend/src/data/jobs.ts`
- `/frontend/src/components/TechnicalInterview.tsx`
- `/frontend/src/components/BehavioralInterview.tsx`
- `/frontend/src/components/ThemeToggle.tsx`
- `/frontend/src/contexts/ThemeContext.tsx`

## 4. Check if backend is running
The frontend makes API calls to `http://localhost:8000`. Make sure the backend is running:
```bash
cd ..
python backend.py
```

## 5. Clear browser cache
Sometimes cached files cause issues. Try:
- Hard refresh: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows)
- Clear browser cache
- Open in incognito/private mode

## 6. Check network tab
In browser DevTools, check the Network tab to see if:
- CSS files are loading
- JavaScript files are loading
- API calls are being made

## 7. Verify dependencies are installed
```bash
cd frontend
npm install
```

## 8. Check for TypeScript errors
```bash
cd frontend
npm run build
```

This will show any TypeScript compilation errors.
