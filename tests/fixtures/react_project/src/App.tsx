import Header from './components/Header';
import { useAuth } from './hooks';

export default function App() {
    const { user } = useAuth();
    return (
        <div>
            <Header />
            <main>Welcome {user?.name}</main>
        </div>
    );
}
