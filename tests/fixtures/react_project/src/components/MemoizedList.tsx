import React from 'react';

export const MemoizedList = React.memo(({ items }: { items: string[] }) => {
    return (
        <ul>
            {items.map((item, i) => <li key={i}>{item}</li>)}
        </ul>
    );
});
