interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

function createMemoryStorage(): StorageLike {
  const store = new Map<string, string>();

  return {
    getItem(key: string) {
      return store.has(key) ? store.get(key)! : null;
    },
    setItem(key: string, value: string) {
      store.set(key, value);
    },
    removeItem(key: string) {
      store.delete(key);
    },
  };
}

function createSafeStorage(kind: 'localStorage' | 'sessionStorage'): StorageLike {
  const memoryStorage = createMemoryStorage();

  const getNativeStorage = (): Storage | null => {
    if (typeof window === 'undefined') {
      return null;
    }

    try {
      return window[kind];
    } catch (error) {
      console.warn(`[storage] ${kind} unavailable, falling back to memory storage`, error);
      return null;
    }
  };

  return {
    getItem(key: string) {
      const nativeStorage = getNativeStorage();
      if (!nativeStorage) {
        return memoryStorage.getItem(key);
      }

      try {
        return nativeStorage.getItem(key);
      } catch (error) {
        console.warn(`[storage] ${kind}.getItem failed for key "${key}"`, error);
        return memoryStorage.getItem(key);
      }
    },
    setItem(key: string, value: string) {
      const nativeStorage = getNativeStorage();
      if (!nativeStorage) {
        memoryStorage.setItem(key, value);
        return;
      }

      try {
        nativeStorage.setItem(key, value);
      } catch (error) {
        console.warn(`[storage] ${kind}.setItem failed for key "${key}"`, error);
        memoryStorage.setItem(key, value);
      }
    },
    removeItem(key: string) {
      const nativeStorage = getNativeStorage();
      if (!nativeStorage) {
        memoryStorage.removeItem(key);
        return;
      }

      try {
        nativeStorage.removeItem(key);
      } catch (error) {
        console.warn(`[storage] ${kind}.removeItem failed for key "${key}"`, error);
        memoryStorage.removeItem(key);
      }
    },
  };
}

export const safeLocalStorage = createSafeStorage('localStorage');
export const safeSessionStorage = createSafeStorage('sessionStorage');
