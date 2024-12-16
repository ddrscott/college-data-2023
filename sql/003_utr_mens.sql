DROP TABLE IF EXISTS utr_mens;
CREATE TABLE utr_mens AS
SELECT *
FROM read_json('data/utr-mens-hits.json',
    maximum_object_size=104857600,
    json_format='json',
    columns={
        'source': 'JSON',
    }
);

