import DashboardCard from '../components/DashboardCard';
import { formatDate } from '@/lib/utils';

export default function Home() {
    return (
        <main>
            <h1>Welcome</h1>
            <DashboardCard title="Overview" />
            <p>{formatDate(new Date())}</p>
        </main>
    );
}
