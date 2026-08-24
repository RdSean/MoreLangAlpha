"""Add seeded K12 homework dictionaries.

Revision ID: 034
Revises: 033
"""

from alembic import op


revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE education_subjects (
            code VARCHAR(16) PRIMARY KEY,
            name VARCHAR(32) NOT NULL UNIQUE,
            color CHAR(7) NOT NULL CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
            sort_order SMALLINT NOT NULL UNIQUE CHECK (sort_order > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE education_homework_types (
            code VARCHAR(16) PRIMARY KEY,
            name VARCHAR(32) NOT NULL UNIQUE,
            sort_order SMALLINT NOT NULL UNIQUE CHECK (sort_order > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE education_subject_homework_types (
            subject_code VARCHAR(16) NOT NULL,
            type_code VARCHAR(16) NOT NULL,
            PRIMARY KEY (subject_code, type_code),
            FOREIGN KEY (subject_code) REFERENCES education_subjects(code)
                ON DELETE RESTRICT,
            FOREIGN KEY (type_code) REFERENCES education_homework_types(code)
                ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE education_grade_levels (
            code VARCHAR(4) PRIMARY KEY,
            name VARCHAR(16) NOT NULL UNIQUE,
            stage VARCHAR(16) NOT NULL CHECK (stage IN ('primary', 'middle', 'high')),
            sort_order SMALLINT NOT NULL UNIQUE CHECK (sort_order BETWEEN 1 AND 12)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE education_practice_sources (
            code VARCHAR(16) PRIMARY KEY,
            name VARCHAR(16) NOT NULL UNIQUE,
            sort_order SMALLINT NOT NULL UNIQUE CHECK (sort_order > 0)
        )
        """
    )

    op.execute(
        """
        INSERT INTO education_subjects (code, name, color, sort_order) VALUES
            ('chinese', '语文', '#D95D39', 1),
            ('math', '数学', '#277DA1', 2),
            ('english', '英语', '#6A994E', 3),
            ('physics', '物理', '#7B61A8', 4),
            ('chemistry', '化学', '#C77D20', 5),
            ('biology', '生物', '#2A9D8F', 6),
            ('history', '历史', '#A44A3F', 7),
            ('geography', '地理', '#3A86A8', 8),
            ('politics', '政治', '#A65E2E', 9)
        """
    )
    op.execute(
        """
        INSERT INTO education_homework_types (code, name, sort_order) VALUES
            ('preview', '预习', 1),
            ('practice', '练习', 2),
            ('read', '阅读', 3),
            ('recite', '背诵', 4),
            ('write', '写作与表达', 5),
            ('review', '订正与复习', 6),
            ('research', '实验与探究', 7),
            ('listen', '听力', 8),
            ('grammar', '语法', 9),
            ('speak', '朗读与口语', 10)
        """
    )
    op.execute(
        """
        INSERT INTO education_subject_homework_types (subject_code, type_code) VALUES
            ('chinese', 'preview'),
            ('chinese', 'practice'),
            ('chinese', 'read'),
            ('chinese', 'recite'),
            ('chinese', 'write'),
            ('chinese', 'review'),
            ('chinese', 'speak'),
            ('math', 'preview'),
            ('math', 'practice'),
            ('math', 'review'),
            ('math', 'research'),
            ('english', 'preview'),
            ('english', 'practice'),
            ('english', 'read'),
            ('english', 'recite'),
            ('english', 'write'),
            ('english', 'review'),
            ('english', 'listen'),
            ('english', 'grammar'),
            ('english', 'speak'),
            ('physics', 'preview'),
            ('physics', 'practice'),
            ('physics', 'review'),
            ('physics', 'research'),
            ('chemistry', 'preview'),
            ('chemistry', 'practice'),
            ('chemistry', 'recite'),
            ('chemistry', 'review'),
            ('chemistry', 'research'),
            ('biology', 'preview'),
            ('biology', 'practice'),
            ('biology', 'read'),
            ('biology', 'recite'),
            ('biology', 'review'),
            ('biology', 'research'),
            ('history', 'preview'),
            ('history', 'practice'),
            ('history', 'read'),
            ('history', 'recite'),
            ('history', 'write'),
            ('history', 'review'),
            ('geography', 'preview'),
            ('geography', 'practice'),
            ('geography', 'read'),
            ('geography', 'recite'),
            ('geography', 'review'),
            ('geography', 'research'),
            ('politics', 'preview'),
            ('politics', 'practice'),
            ('politics', 'read'),
            ('politics', 'recite'),
            ('politics', 'write'),
            ('politics', 'review')
        """
    )
    op.execute(
        """
        INSERT INTO education_grade_levels (code, name, stage, sort_order) VALUES
            ('g1', '一年级', 'primary', 1),
            ('g2', '二年级', 'primary', 2),
            ('g3', '三年级', 'primary', 3),
            ('g4', '四年级', 'primary', 4),
            ('g5', '五年级', 'primary', 5),
            ('g6', '六年级', 'primary', 6),
            ('g7', '初一', 'middle', 7),
            ('g8', '初二', 'middle', 8),
            ('g9', '初三', 'middle', 9),
            ('g10', '高一', 'high', 10),
            ('g11', '高二', 'high', 11),
            ('g12', '高三', 'high', 12)
        """
    )
    op.execute(
        """
        INSERT INTO education_practice_sources (code, name, sort_order) VALUES
            ('schoolwork', '校内作业', 1),
            ('homework', '校外作业', 2)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE education_subject_homework_types")
    op.execute("DROP TABLE education_practice_sources")
    op.execute("DROP TABLE education_grade_levels")
    op.execute("DROP TABLE education_homework_types")
    op.execute("DROP TABLE education_subjects")
