UPDATE schools SET
    utr_id = source.id
FROM utr_mens
WHERE
        STABBR = source.location.stateAbbr 
    AND source.school.displayName = instnm
AND schools.utr_id is null;
