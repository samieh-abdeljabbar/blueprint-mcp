import { useAuth } from '../hooks';

export default function Header() {
    const { user } = useAuth();
    return (
        <header>
            <nav>
                <span>{user?.name}</span>
            </nav>
        </header>
    );
}
