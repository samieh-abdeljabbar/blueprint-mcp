'use client'

import { createContext, useContext, useState } from 'react';

export const ThemeContext = createContext<string>('light');

export function useTheme() {
    const theme = useContext(ThemeContext);
    const [current, setCurrent] = useState(theme);
    return { current, setCurrent };
}
