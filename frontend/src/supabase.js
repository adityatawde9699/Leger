import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
const isDev = import.meta.env.VITE_AUTH_PROVIDER === "dev";

if (!isDev && (!supabaseUrl || !supabaseAnonKey)) {
  console.error("Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY. Authentication will fail.");
}

export const supabase = !isDev
  ? createClient(supabaseUrl || "", supabaseAnonKey || "")
  : {
      auth: {
        getSession: async () => ({ data: { session: null } }),
        onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
        signOut: async () => {},
      }
    };
