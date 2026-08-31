import { getApp, getApps, initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider } from "firebase/auth";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

const missingConfig = Object.entries(firebaseConfig)
  .filter(([, value]) => !value)
  .map(([key]) => key);

if (import.meta.env.VITE_AUTH_PROVIDER === "firebase" && missingConfig.length) {
  console.error(`Missing Firebase configuration: ${missingConfig.join(", ")}`);
}

const isFirebase = import.meta.env.VITE_AUTH_PROVIDER === "firebase";
const app = isFirebase
  ? (getApps().length ? getApp() : initializeApp(firebaseConfig))
  : null;
export const firebaseAuth = app ? getAuth(app) : null;
export const googleProvider = new GoogleAuthProvider();