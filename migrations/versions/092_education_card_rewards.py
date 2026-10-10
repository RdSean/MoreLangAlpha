"""Durable homework reward wallets, card packs and student collections."""

from alembic import op

revision = "092_education_card_rewards"
down_revision = "091_pokemon_cards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE education_reward_settings (
            household_id UUID PRIMARY KEY REFERENCES education_households ON DELETE CASCADE,
            daily_price INTEGER NOT NULL DEFAULT 5 CHECK (daily_price BETWEEN 1 AND 10000),
            featured_price INTEGER NOT NULL DEFAULT 15 CHECK (featured_price BETWEEN 1 AND 10000),
            rare_price INTEGER NOT NULL DEFAULT 30 CHECK (rare_price BETWEEN 1 AND 10000),
            activated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by_user_id VARCHAR(255) REFERENCES users
        );
        INSERT INTO education_reward_settings (household_id) SELECT household_id FROM education_households;

        CREATE TABLE education_reward_wallets (
            household_id UUID NOT NULL,
            student_id VARCHAR(255) NOT NULL,
            balance BIGINT NOT NULL DEFAULT 0 CHECK (balance >= 0),
            homework_points BIGINT NOT NULL DEFAULT 0 CHECK (homework_points >= 0),
            started_on DATE NOT NULL,
            settled_through DATE NOT NULL,
            streak INTEGER NOT NULL DEFAULT 0 CHECK (streak >= 0),
            streak_run_id UUID NOT NULL,
            PRIMARY KEY (household_id, student_id),
            FOREIGN KEY (household_id, student_id) REFERENCES education_memberships ON DELETE CASCADE
        );
        INSERT INTO education_reward_wallets (household_id, student_id, started_on, settled_through, streak_run_id)
        SELECT m.household_id, m.user_id,
               (GREATEST(s.activated_at, m.created_at) AT TIME ZONE h.timezone)::date,
               (GREATEST(s.activated_at, m.created_at) AT TIME ZONE h.timezone)::date - 1,
               gen_random_uuid()
        FROM education_memberships m JOIN education_households h USING (household_id)
        JOIN education_reward_settings s USING (household_id) WHERE m.role = 'student';

        CREATE TABLE education_reward_card_packs (
            pack_id UUID PRIMARY KEY,
            household_id UUID NOT NULL,
            student_id VARCHAR(255) NOT NULL,
            source TEXT NOT NULL CHECK (source IN ('daily','streak','purchase')),
            pack_type TEXT NOT NULL CHECK (pack_type IN ('daily','featured','rare')),
            reward_date DATE NOT NULL,
            streak_node INTEGER,
            price INTEGER CHECK (price BETWEEN 1 AND 10000),
            idempotency_key UUID,
            probabilities JSONB NOT NULL,
            policy_version TEXT NOT NULL,
            card_id UUID REFERENCES education_pokemon_cards ON DELETE RESTRICT,
            reward_level TEXT CHECK (reward_level IN ('basic','rare','featured','premium','legendary')),
            owned_before INTEGER CHECK (owned_before >= 0),
            returned_points INTEGER NOT NULL DEFAULT 0 CHECK (returned_points >= 0),
            effective_probabilities JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            opened_at TIMESTAMPTZ,
            FOREIGN KEY (household_id, student_id) REFERENCES education_reward_wallets ON DELETE CASCADE,
            CHECK ((source = 'purchase') = (price IS NOT NULL AND idempotency_key IS NOT NULL)),
            CHECK ((source = 'streak') = (streak_node IS NOT NULL)),
            CHECK ((opened_at IS NULL) = (card_id IS NULL)),
            CHECK (card_id IS NULL OR (reward_level IS NOT NULL AND owned_before IS NOT NULL))
        );
        CREATE UNIQUE INDEX education_reward_daily_unique ON education_reward_card_packs
            (household_id, student_id, reward_date, source) WHERE source IN ('daily','streak');
        CREATE UNIQUE INDEX education_reward_purchase_unique ON education_reward_card_packs
            (household_id, student_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
        CREATE INDEX education_reward_packs_student_idx ON education_reward_card_packs
            (household_id, student_id, created_at DESC, pack_id);

        CREATE TABLE education_reward_point_entries (
            entry_id UUID PRIMARY KEY,
            household_id UUID NOT NULL,
            student_id VARCHAR(255) NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('homework','purchase','duplicate')),
            amount INTEGER NOT NULL,
            task_id UUID REFERENCES education_tasks ON DELETE RESTRICT,
            pack_id UUID REFERENCES education_reward_card_packs ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (household_id, student_id) REFERENCES education_reward_wallets ON DELETE CASCADE,
            CHECK ((kind = 'homework' AND amount = 1 AND task_id IS NOT NULL AND pack_id IS NULL)
                OR (kind = 'purchase' AND amount < 0 AND pack_id IS NOT NULL AND task_id IS NULL)
                OR (kind = 'duplicate' AND amount > 0 AND pack_id IS NOT NULL AND task_id IS NULL))
        );
        CREATE UNIQUE INDEX education_reward_task_credit_unique ON education_reward_point_entries(task_id)
            WHERE kind = 'homework';
        CREATE UNIQUE INDEX education_reward_pack_entry_unique ON education_reward_point_entries(pack_id, kind)
            WHERE pack_id IS NOT NULL;
        CREATE INDEX education_reward_entries_student_idx ON education_reward_point_entries
            (household_id, student_id, created_at DESC, entry_id);
        INSERT INTO education_reward_point_entries (entry_id, household_id, student_id, kind, amount, task_id)
        SELECT gen_random_uuid(), t.household_id, t.assigned_student_id, 'homework', 1, t.task_id
        FROM education_tasks t JOIN education_households h USING (household_id)
        JOIN education_reward_wallets w ON w.household_id=t.household_id AND w.student_id=t.assigned_student_id
        WHERE t.status='completed' AND t.occurrence_date <= (NOW() AT TIME ZONE h.timezone)::date;
        UPDATE education_reward_wallets w SET balance=q.points, homework_points=q.points
        FROM (SELECT household_id, student_id, count(*) AS points FROM education_reward_point_entries
              GROUP BY household_id, student_id) q
        WHERE w.household_id=q.household_id AND w.student_id=q.student_id;

        CREATE TABLE education_reward_days (
            household_id UUID NOT NULL,
            student_id VARCHAR(255) NOT NULL,
            reward_date DATE NOT NULL,
            timezone TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('completed','missed','empty')),
            task_ids UUID[] NOT NULL,
            streak INTEGER NOT NULL CHECK (streak >= 0),
            streak_run_id UUID NOT NULL,
            settled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (household_id, student_id, reward_date),
            FOREIGN KEY (household_id, student_id) REFERENCES education_reward_wallets ON DELETE CASCADE
        );
        CREATE TABLE education_student_pokemon_cards (
            household_id UUID NOT NULL,
            student_id VARCHAR(255) NOT NULL,
            card_id UUID NOT NULL REFERENCES education_pokemon_cards ON DELETE RESTRICT,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            first_obtained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_obtained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (household_id, student_id, card_id),
            FOREIGN KEY (household_id, student_id) REFERENCES education_reward_wallets ON DELETE CASCADE
        );
        CREATE TABLE education_pokemon_reward_levels (
            card_id UUID PRIMARY KEY REFERENCES education_pokemon_cards ON DELETE CASCADE,
            reward_level TEXT NOT NULL CHECK (reward_level IN ('basic','rare','featured','premium','legendary'))
        );
        INSERT INTO education_pokemon_reward_levels (card_id,reward_level)
        SELECT card_id, CASE
          WHEN rarity IN ('普通','非普通') THEN 'basic'
          WHEN rarity IN ('稀有','皮卡丘稀有') THEN 'rare'
          WHEN rarity IN ('插画稀有','未来稀有','惊人稀有') THEN 'featured'
          WHEN rarity IN ('特别插画稀有','LEGEND 传说','秘密稀有','超稀有') THEN 'legendary'
          ELSE 'premium' END
        FROM education_pokemon_cards WHERE rarity IN (
          '普通','非普通','稀有','皮卡丘稀有','插画稀有','未来稀有','惊人稀有',
          '特别插画稀有','LEGEND 传说','秘密稀有','超稀有','双倍稀有','稀有（闪光）',
          '稀有（闪光）GX','稀有（闪光）EX','闪光稀有 VMAX','BREAK 稀有','稀有 Prime',
          '稀有（闪光）ex','闪光稀有 V','闪光稀有 VSTAR','稀有（闪光）LV.X');
    """)


def downgrade() -> None:
    for table in (
        "education_pokemon_reward_levels",
        "education_student_pokemon_cards",
        "education_reward_days",
        "education_reward_point_entries",
        "education_reward_card_packs",
        "education_reward_wallets",
        "education_reward_settings",
    ):
        op.execute(f"DROP TABLE {table}")
