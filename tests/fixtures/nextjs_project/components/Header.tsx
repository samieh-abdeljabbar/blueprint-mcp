import Link from './Link';

export default function Header() {
    return (
        <header>
            <Link href="/">Home</Link>
            <Link href="/dashboard">Dashboard</Link>
        </header>
    );
}
