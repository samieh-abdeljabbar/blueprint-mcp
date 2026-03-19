import DashboardCard from '@components/DashboardCard';

export default function DashboardDetail({ params }: { params: { id: string } }) {
    return (
        <div>
            Dashboard item {params.id}
            <DashboardCard title={params.id} />
        </div>
    );
}
