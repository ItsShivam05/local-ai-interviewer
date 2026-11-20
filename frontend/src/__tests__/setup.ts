import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

// findBy* / waitFor give up after 1 s by default. Whole-page tests on a busy machine or a CI runner can need longer to settle;
// a real failure still fails, just later.
configure({ asyncUtilTimeout: 5000 });
