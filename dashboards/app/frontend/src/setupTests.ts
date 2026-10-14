import '@testing-library/jest-dom';

// Ensure test runner contracts default to English
if (typeof window !== 'undefined' && window.localStorage) {
  window.localStorage.setItem('app_lang', 'en');
}
