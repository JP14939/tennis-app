import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

// expo-secure-store's native APIs aren't available on web — fall back to
// localStorage there so the same calling code works in both.
export const storage = Platform.OS === 'web'
  ? {
      getItem: async (key) => localStorage.getItem(key),
      setItem: async (key, value) => localStorage.setItem(key, value),
      deleteItem: async (key) => localStorage.removeItem(key),
    }
  : {
      getItem: SecureStore.getItemAsync,
      setItem: SecureStore.setItemAsync,
      deleteItem: SecureStore.deleteItemAsync,
    };
