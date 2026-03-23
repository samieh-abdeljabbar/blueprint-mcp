import { useAuth } from '../hooks';
import { useAuthStore } from '../stores/useAuthStore';
import { useThemeStore } from '../stores/useThemeStore';

export default function Header() {
    const { user } = useAuth();
    const { logout } = useAuthStore();
    const { theme, toggleTheme } = useThemeStore();
    return (
        <header className={theme}>
            <nav>
                <span>{user?.name}</span>
                <button onClick={logout}>Logout</button>
                <button onClick={toggleTheme}>Toggle Theme</button>
            </nav>
        </header>
    );
}
